use std::time::Duration;

use reqwest::StatusCode;
use reqwest::blocking::Client;
use reqwest::header::{AUTHORIZATION, CONTENT_TYPE, HeaderMap, HeaderValue, InvalidHeaderValue};
use thiserror::Error;

use crate::config::Config;
use crate::telemetrie::Telemetrie;

const TIMEOUT: Duration = Duration::from_secs(10);

#[derive(Debug, Error)]
pub enum ErreurEnvoi {
    #[error("clé API invalide dans un en-tête HTTP")]
    CleInvalide(#[from] InvalidHeaderValue),
    #[error("erreur réseau : {0}")]
    Reseau(#[from] reqwest::Error),
    #[error("sérialisation JSON impossible : {0}")]
    Serialisation(#[from] serde_json::Error),
    #[error("Supabase a refusé la requête ({statut}) : {corps}")]
    Rejet { statut: StatusCode, corps: String },
}

impl ErreurEnvoi {
    pub fn est_temporaire(&self) -> bool {
        match self {
            Self::Reseau(_) => true,
            Self::Rejet { statut, .. } => {
                statut.is_server_error()
                    || *statut == StatusCode::TOO_MANY_REQUESTS
                    || *statut == StatusCode::REQUEST_TIMEOUT
            }
            Self::CleInvalide(_) | Self::Serialisation(_) => false,
        }
    }

    pub fn statut(&self) -> Option<u16> {
        match self {
            Self::Rejet { statut, .. } => Some(statut.as_u16()),
            Self::Reseau(erreur) => erreur.status().map(|statut| statut.as_u16()),
            Self::CleInvalide(_) | Self::Serialisation(_) => None,
        }
    }
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct RapportEnvoi {
    pub statut: u16,
    pub octets: usize,
}

pub struct ClientSupabase {
    http: Client,
    url_table: String,
}

impl ClientSupabase {
    pub fn new(config: &Config) -> Result<Self, ErreurEnvoi> {
        let http = Client::builder()
            .default_headers(entetes(&config.supabase_cle)?)
            .timeout(TIMEOUT)
            .build()?;

        Ok(Self {
            http,
            url_table: format!("{}/rest/v1/telemetrie", config.supabase_url),
        })
    }

    pub fn envoyer(&self, lot: &[Telemetrie]) -> Result<RapportEnvoi, ErreurEnvoi> {
        let corps = serde_json::to_string(lot)?;
        let octets = corps.len();

        let reponse = self
            .http
            .post(&self.url_table)
            .header(CONTENT_TYPE, "application/json")
            .header("Prefer", "resolution=ignore-duplicates,return=minimal")
            .body(corps)
            .send()?;

        let statut = reponse.status();
        if statut.is_success() {
            return Ok(RapportEnvoi {
                statut: statut.as_u16(),
                octets,
            });
        }

        let corps = reponse.text().unwrap_or_default();
        Err(ErreurEnvoi::Rejet { statut, corps })
    }
}

fn entetes(cle: &str) -> Result<HeaderMap, InvalidHeaderValue> {
    let mut entetes = HeaderMap::new();

    let mut apikey = HeaderValue::from_str(cle)?;
    apikey.set_sensitive(true);
    entetes.insert("apikey", apikey);

    if cle.starts_with("eyJ") {
        let mut bearer = HeaderValue::from_str(&format!("Bearer {cle}"))?;
        bearer.set_sensitive(true);
        entetes.insert(AUTHORIZATION, bearer);
    }

    Ok(entetes)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn une_cle_publishable_ne_va_pas_dans_authorization() {
        let entetes = entetes("sb_publishable_abc").unwrap();
        assert!(entetes.contains_key("apikey"));
        assert!(!entetes.contains_key(AUTHORIZATION));
    }

    #[test]
    fn une_ancienne_cle_jwt_va_dans_les_deux_entetes() {
        let entetes = entetes("eyJabc").unwrap();
        assert!(entetes.contains_key("apikey"));
        assert_eq!(entetes[AUTHORIZATION], "Bearer eyJabc");
    }

    #[test]
    fn distingue_erreur_temporaire_et_definitive() {
        let rejet = |statut| ErreurEnvoi::Rejet {
            statut,
            corps: String::new(),
        };
        assert!(rejet(StatusCode::SERVICE_UNAVAILABLE).est_temporaire());
        assert!(!rejet(StatusCode::UNAUTHORIZED).est_temporaire());
        assert_eq!(rejet(StatusCode::UNAUTHORIZED).statut(), Some(401));
    }
}
