use chrono::{DateTime, Utc};
use serde::Serialize;

#[derive(Debug, Clone, PartialEq, Serialize)]
pub struct Telemetrie {
    pub horodatage: DateTime<Utc>,
    pub statut_occupation: bool,
    pub poids: f64,
    pub temperature: f64,
}

#[cfg(test)]
mod tests {
    use super::*;
    use chrono::TimeZone;
    use serde_json::json;

    #[test]
    fn serialise_avec_les_noms_de_colonnes() {
        let mesure = Telemetrie {
            horodatage: Utc.with_ymd_and_hms(2026, 1, 2, 3, 4, 5).unwrap(),
            statut_occupation: true,
            poids: 72.5,
            temperature: 30.25,
        };

        assert_eq!(
            serde_json::to_value(&mesure).unwrap(),
            json!({
                "horodatage": "2026-01-02T03:04:05Z",
                "statut_occupation": true,
                "poids": 72.5,
                "temperature": 30.25
            })
        );
    }
}
