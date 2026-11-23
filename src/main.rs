mod bruit;
mod capteurs;
mod chaise;
mod client_http;
mod config;
mod pilotage;
mod telemetrie;

use std::collections::VecDeque;
use std::env;
use std::error::Error;
use std::io::{self, Write};
use std::process::ExitCode;
use std::sync::mpsc::{Receiver, RecvTimeoutError};
use std::thread;
use std::time::{Duration, Instant};

use chaise::Chaise;
use client_http::ClientSupabase;
use config::Config;
use pilotage::Commande;
use rand::Rng;
use serde::Serialize;
use telemetrie::Telemetrie;

const CAPACITE_TAMPON: usize = 720;
const TAILLE_MAX_LOT: usize = 100;
const INTERVALLE_MAX_SECS: u64 = 3600;

#[derive(Debug, Clone, Copy, Serialize)]
struct BilanEnvoi {
    reussi: bool,
    statut: Option<u16>,
    duree_ms: u64,
    mesures: usize,
    octets: usize,
}

fn main() -> ExitCode {
    match lancer() {
        Ok(()) => ExitCode::SUCCESS,
        Err(erreur) => {
            eprintln!("Erreur fatale : {erreur}");
            ExitCode::FAILURE
        }
    }
}

fn lancer() -> Result<(), Box<dyn Error>> {
    dotenvy::dotenv().ok();

    let config = Config::depuis_env()?;
    let client = ClientSupabase::new(&config)?;
    let mut rng = rand::rng();
    let mut chaise = Chaise::new(&mut rng);
    let mut tampon: VecDeque<Telemetrie> = VecDeque::with_capacity(CAPACITE_TAMPON);
    let mut intervalle = config.intervalle;
    let commandes = env::args()
        .any(|argument| argument == "--pilote")
        .then(pilotage::ecouter_commandes);

    match &commandes {
        Some(recepteur) => match recepteur.recv() {
            Ok(commande) => appliquer(commande, &mut chaise, &mut intervalle, &mut rng),
            Err(_) => return Ok(()),
        },
        None => println!(
            "Simulateur démarré : une mesure toutes les {} s (Ctrl+C pour arrêter).",
            intervalle.as_secs()
        ),
    }

    let mut precedente = Instant::now();

    loop {
        let debut = Instant::now();
        let ecoule = debut.duration_since(precedente);
        precedente = debut;

        let mesure = chaise.mesurer(ecoule, &mut rng);
        let apercu = mesure.clone();

        if tampon.len() == CAPACITE_TAMPON {
            tampon.pop_front();
            eprintln!("Tampon plein : mesure la plus ancienne abandonnée.");
        }
        tampon.push_back(mesure);

        let bilan = vider_tampon(&client, &mut tampon)?;
        afficher(&apercu, tampon.len(), bilan, commandes.is_some());

        let restant = intervalle.saturating_sub(debut.elapsed());
        match &commandes {
            None => thread::sleep(restant),
            Some(recepteur) => {
                if !attendre(recepteur, restant, &mut chaise, &mut intervalle, &mut rng) {
                    if !tampon.is_empty() {
                        vider_tampon(&client, &mut tampon)?;
                    }
                    return Ok(());
                }
            }
        }
    }
}

fn attendre<R: Rng>(
    recepteur: &Receiver<Commande>,
    delai: Duration,
    chaise: &mut Chaise,
    intervalle: &mut Duration,
    rng: &mut R,
) -> bool {
    match recepteur.recv_timeout(delai) {
        Ok(commande) => {
            appliquer(commande, chaise, intervalle, rng);
            while let Ok(suivante) = recepteur.try_recv() {
                appliquer(suivante, chaise, intervalle, rng);
            }
            true
        }
        Err(RecvTimeoutError::Timeout) => true,
        Err(RecvTimeoutError::Disconnected) => false,
    }
}

fn appliquer<R: Rng>(
    commande: Commande,
    chaise: &mut Chaise,
    intervalle: &mut Duration,
    rng: &mut R,
) {
    let nom = match commande {
        Commande::Aleatoire => {
            chaise.passer_en_aleatoire(rng);
            "aleatoire"
        }
        Commande::Manuel { .. } => {
            if let Some(valeurs) = commande.valeurs_manuelles() {
                chaise.passer_en_manuel(valeurs);
            }
            "manuel"
        }
        Commande::Intervalle { secondes } => {
            *intervalle = Duration::from_secs(secondes.clamp(1, INTERVALLE_MAX_SECS));
            "intervalle"
        }
    };

    let ligne = serde_json::json!({ "accuse": nom }).to_string();
    let _ = writeln!(io::stdout(), "{ligne}");
}

fn afficher(mesure: &Telemetrie, en_attente: usize, bilan: BilanEnvoi, pilote: bool) {
    let ligne = if pilote {
        serde_json::json!({ "mesure": mesure, "en_attente": en_attente, "envoi": bilan })
            .to_string()
    } else {
        format!(
            "{} | {} | {:>6.2} kg | {:>5.2} °C",
            mesure.horodatage.format("%H:%M:%S"),
            if mesure.statut_occupation {
                "occupée"
            } else {
                "vide   "
            },
            mesure.poids,
            mesure.temperature,
        )
    };

    let _ = writeln!(io::stdout(), "{ligne}");
}

fn vider_tampon(
    client: &ClientSupabase,
    tampon: &mut VecDeque<Telemetrie>,
) -> Result<BilanEnvoi, client_http::ErreurEnvoi> {
    let taille = tampon.len().min(TAILLE_MAX_LOT);
    let lot = &tampon.make_contiguous()[..taille];
    let debut = Instant::now();
    let resultat = client.envoyer(lot);
    let duree_ms = u64::try_from(debut.elapsed().as_millis()).unwrap_or(u64::MAX);

    match resultat {
        Ok(rapport) => {
            tampon.drain(..taille);
            Ok(BilanEnvoi {
                reussi: true,
                statut: Some(rapport.statut),
                duree_ms,
                mesures: taille,
                octets: rapport.octets,
            })
        }
        Err(erreur) if erreur.est_temporaire() => {
            eprintln!("Envoi différé ({} en attente) : {erreur}", tampon.len());
            Ok(BilanEnvoi {
                reussi: false,
                statut: erreur.statut(),
                duree_ms,
                mesures: taille,
                octets: 0,
            })
        }
        Err(erreur) => Err(erreur),
    }
}
