use std::env;
use std::time::Duration;

use thiserror::Error;

const INTERVALLE_DEFAUT_SECS: u64 = 5;

#[derive(Debug, Error)]
pub enum ErreurConfig {
    #[error("variable d'environnement manquante ou vide : {0} (voir .env.exemple)")]
    Manquante(&'static str),
    #[error("{nom} contient encore la valeur d'exemple : remplacez-la dans .env")]
    NonRemplacee { nom: &'static str },
    #[error("SUPABASE_URL doit commencer par http:// ou https://")]
    UrlInvalide,
    #[error("SUPABASE_ANON_KEY contient une clé secrète : utilisez la clé publique")]
    CleSecrete,
    #[error("INTERVALLE_SECONDES doit être un entier supérieur ou égal à 1")]
    IntervalleInvalide,
}

pub struct Config {
    pub supabase_url: String,
    pub supabase_cle: String,
    pub intervalle: Duration,
}

impl Config {
    pub fn depuis_env() -> Result<Self, ErreurConfig> {
        let url = variable_requise("SUPABASE_URL")?;
        let cle = variable_requise("SUPABASE_ANON_KEY")?;
        let intervalle = env::var("INTERVALLE_SECONDES").ok();

        Self::valider(url, cle, intervalle.as_deref())
    }

    fn valider(url: String, cle: String, intervalle: Option<&str>) -> Result<Self, ErreurConfig> {
        if url.contains("votre-projet") {
            return Err(ErreurConfig::NonRemplacee {
                nom: "SUPABASE_URL",
            });
        }
        if cle == "votre-cle-publique" {
            return Err(ErreurConfig::NonRemplacee {
                nom: "SUPABASE_ANON_KEY",
            });
        }
        if !url.starts_with("http://") && !url.starts_with("https://") {
            return Err(ErreurConfig::UrlInvalide);
        }
        if cle.starts_with("sb_secret_") {
            return Err(ErreurConfig::CleSecrete);
        }

        let secondes = match intervalle {
            None => INTERVALLE_DEFAUT_SECS,
            Some(texte) => texte
                .trim()
                .parse::<u64>()
                .ok()
                .filter(|&s| s >= 1)
                .ok_or(ErreurConfig::IntervalleInvalide)?,
        };

        Ok(Self {
            supabase_url: url.trim_end_matches('/').to_owned(),
            supabase_cle: cle,
            intervalle: Duration::from_secs(secondes),
        })
    }
}

fn variable_requise(nom: &'static str) -> Result<String, ErreurConfig> {
    env::var(nom)
        .ok()
        .map(|valeur| valeur.trim().to_owned())
        .filter(|valeur| !valeur.is_empty())
        .ok_or(ErreurConfig::Manquante(nom))
}

#[cfg(test)]
mod tests {
    use super::*;

    fn valider(url: &str, cle: &str, intervalle: Option<&str>) -> Result<Config, ErreurConfig> {
        Config::valider(url.to_owned(), cle.to_owned(), intervalle)
    }

    #[test]
    fn retire_le_slash_final_et_applique_le_defaut() {
        let config = valider("https://abc.supabase.co/", "sb_publishable_x", None).unwrap();
        assert_eq!(config.supabase_url, "https://abc.supabase.co");
        assert_eq!(config.intervalle, Duration::from_secs(5));
    }

    #[test]
    fn refuse_une_cle_secrete() {
        let resultat = valider("https://abc.supabase.co", "sb_secret_x", None);
        assert!(matches!(resultat, Err(ErreurConfig::CleSecrete)));
    }

    #[test]
    fn refuse_un_intervalle_nul() {
        let resultat = valider("https://abc.supabase.co", "cle", Some("0"));
        assert!(matches!(resultat, Err(ErreurConfig::IntervalleInvalide)));
    }
}
