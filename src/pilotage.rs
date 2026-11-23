use std::io::{self, BufRead};
use std::sync::mpsc::{self, Receiver};
use std::thread;

use serde::Deserialize;

use crate::chaise::ValeursManuelles;

#[derive(Debug, Clone, Copy, PartialEq, Deserialize)]
#[serde(tag = "commande", rename_all = "snake_case")]
pub enum Commande {
    Aleatoire,
    Manuel {
        occupee: bool,
        poids: f64,
        temperature: f64,
    },
    Intervalle {
        secondes: u64,
    },
}

impl Commande {
    pub fn valeurs_manuelles(self) -> Option<ValeursManuelles> {
        match self {
            Self::Manuel {
                occupee,
                poids,
                temperature,
            } => Some(ValeursManuelles {
                occupee,
                poids,
                temperature,
            }),
            Self::Aleatoire | Self::Intervalle { .. } => None,
        }
    }
}

pub fn ecouter_commandes() -> Receiver<Commande> {
    let (emetteur, recepteur) = mpsc::channel();

    thread::spawn(move || {
        for ligne in io::stdin().lock().lines() {
            let Ok(ligne) = ligne else { break };
            match serde_json::from_str::<Commande>(&ligne) {
                Ok(commande) => {
                    if emetteur.send(commande).is_err() {
                        break;
                    }
                }
                Err(erreur) => eprintln!("Commande ignorée : {erreur}"),
            }
        }
    });

    recepteur
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn lit_une_commande_manuelle() {
        let commande: Commande = serde_json::from_str(
            r#"{"commande":"manuel","occupee":true,"poids":72.5,"temperature":30.0}"#,
        )
        .unwrap();

        assert_eq!(
            commande.valeurs_manuelles(),
            Some(ValeursManuelles {
                occupee: true,
                poids: 72.5,
                temperature: 30.0,
            })
        );
    }

    #[test]
    fn lit_les_autres_commandes() {
        let aleatoire: Commande = serde_json::from_str(r#"{"commande":"aleatoire"}"#).unwrap();
        let intervalle: Commande =
            serde_json::from_str(r#"{"commande":"intervalle","secondes":2}"#).unwrap();

        assert_eq!(aleatoire, Commande::Aleatoire);
        assert_eq!(intervalle, Commande::Intervalle { secondes: 2 });
    }

    #[test]
    fn refuse_une_commande_inconnue() {
        assert!(serde_json::from_str::<Commande>(r#"{"commande":"exploser"}"#).is_err());
    }
}
