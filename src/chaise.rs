use std::time::Duration;

use chrono::Utc;
use rand::{Rng, RngExt};

use crate::capteurs::{
    Capteur, CapteurPoids, CapteurPresence, CapteurTemperature, EtatPhysique, Occupant,
};
use crate::telemetrie::Telemetrie;

const TEMPERATURE_AMBIANTE: f64 = 21.0;
const TEMPERATURE_CONTACT: f64 = 33.0;
const CONSTANTE_CHAUFFE_SECS: f64 = 120.0;
const CONSTANTE_REFROIDISSEMENT_SECS: f64 = 240.0;

const DUREE_ASSISE_SECS: std::ops::RangeInclusive<f64> = 60.0..=240.0;
const DUREE_VIDE_SECS: std::ops::RangeInclusive<f64> = 30.0..=120.0;
const POIDS_OCCUPANT_KG: std::ops::RangeInclusive<f64> = 50.0..=110.0;

#[derive(Debug, Clone, Copy, PartialEq)]
pub struct ValeursManuelles {
    pub occupee: bool,
    pub poids: f64,
    pub temperature: f64,
}

#[derive(Debug)]
pub struct Chaise {
    etat: EtatPhysique,
    manuel: Option<ValeursManuelles>,
    secondes_avant_transition: f64,
    presence: CapteurPresence,
    poids: CapteurPoids,
    temperature: CapteurTemperature,
}

impl Chaise {
    pub fn new<R: Rng>(rng: &mut R) -> Self {
        Self {
            etat: EtatPhysique {
                occupant: None,
                temperature_assise: TEMPERATURE_AMBIANTE,
            },
            manuel: None,
            secondes_avant_transition: rng.random_range(DUREE_VIDE_SECS),
            presence: CapteurPresence::new(0.02),
            poids: CapteurPoids::new(),
            temperature: CapteurTemperature::new(),
        }
    }

    pub fn passer_en_manuel(&mut self, valeurs: ValeursManuelles) {
        self.manuel = Some(ValeursManuelles {
            occupee: valeurs.occupee,
            poids: if valeurs.occupee {
                valeurs.poids.clamp(0.0, 300.0)
            } else {
                0.0
            },
            temperature: valeurs.temperature.clamp(-20.0, 80.0),
        });
    }

    pub fn passer_en_aleatoire<R: Rng>(&mut self, rng: &mut R) {
        if let Some(valeurs) = self.manuel.take() {
            self.etat.occupant = valeurs.occupee.then_some(Occupant {
                poids_kg: valeurs.poids,
            });
            self.etat.temperature_assise = valeurs.temperature;
            self.secondes_avant_transition = if valeurs.occupee {
                rng.random_range(DUREE_ASSISE_SECS)
            } else {
                rng.random_range(DUREE_VIDE_SECS)
            };
        }
    }

    pub fn mesurer<R: Rng>(&mut self, dt: Duration, rng: &mut R) -> Telemetrie {
        if let Some(valeurs) = self.manuel {
            return Telemetrie {
                horodatage: Utc::now(),
                statut_occupation: valeurs.occupee,
                poids: valeurs.poids,
                temperature: valeurs.temperature,
            };
        }

        self.avancer(dt.as_secs_f64(), rng);

        Telemetrie {
            horodatage: Utc::now(),
            statut_occupation: self.presence.lire(&self.etat, rng),
            poids: self.poids.lire(&self.etat, rng),
            temperature: self.temperature.lire(&self.etat, rng),
        }
    }

    fn avancer<R: Rng>(&mut self, dt: f64, rng: &mut R) {
        self.secondes_avant_transition -= dt;
        if self.secondes_avant_transition <= 0.0 {
            self.basculer_occupation(rng);
        }

        let (cible, constante) = match self.etat.occupant {
            Some(_) => (TEMPERATURE_CONTACT, CONSTANTE_CHAUFFE_SECS),
            None => (TEMPERATURE_AMBIANTE, CONSTANTE_REFROIDISSEMENT_SECS),
        };
        let progression = 1.0 - (-dt / constante).exp();
        self.etat.temperature_assise += (cible - self.etat.temperature_assise) * progression;
    }

    fn basculer_occupation<R: Rng>(&mut self, rng: &mut R) {
        let (occupant, duree) = match self.etat.occupant {
            Some(_) => (None, rng.random_range(DUREE_VIDE_SECS)),
            None => {
                let poids_kg = rng.random_range(POIDS_OCCUPANT_KG);
                (
                    Some(Occupant { poids_kg }),
                    rng.random_range(DUREE_ASSISE_SECS),
                )
            }
        };
        self.etat.occupant = occupant;
        self.secondes_avant_transition = duree;
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use rand::SeedableRng;
    use rand::rngs::StdRng;

    #[test]
    fn la_simulation_reste_dans_les_bornes_de_la_base() {
        let mut rng = StdRng::seed_from_u64(7);
        let mut chaise = Chaise::new(&mut rng);
        let mut vue_occupee = false;

        for _ in 0..5_000 {
            let mesure = chaise.mesurer(Duration::from_secs(5), &mut rng);
            vue_occupee |= mesure.statut_occupation;
            assert!((0.0..=300.0).contains(&mesure.poids));
            assert!((-20.0..=80.0).contains(&mesure.temperature));
        }
        assert!(vue_occupee);
    }

    #[test]
    fn le_mode_manuel_envoie_les_valeurs_exactes() {
        let mut rng = StdRng::seed_from_u64(8);
        let mut chaise = Chaise::new(&mut rng);
        chaise.passer_en_manuel(ValeursManuelles {
            occupee: true,
            poids: 72.5,
            temperature: 30.0,
        });

        let mesure = chaise.mesurer(Duration::from_secs(5), &mut rng);

        assert!(mesure.statut_occupation);
        assert_eq!(mesure.poids, 72.5);
        assert_eq!(mesure.temperature, 30.0);
    }

    #[test]
    fn une_chaise_vide_pese_zero_en_manuel() {
        let mut rng = StdRng::seed_from_u64(9);
        let mut chaise = Chaise::new(&mut rng);
        chaise.passer_en_manuel(ValeursManuelles {
            occupee: false,
            poids: 80.0,
            temperature: 22.0,
        });

        assert_eq!(chaise.mesurer(Duration::from_secs(5), &mut rng).poids, 0.0);
    }

    #[test]
    fn le_retour_en_aleatoire_repart_des_valeurs_manuelles() {
        let mut rng = StdRng::seed_from_u64(10);
        let mut chaise = Chaise::new(&mut rng);
        chaise.passer_en_manuel(ValeursManuelles {
            occupee: true,
            poids: 90.0,
            temperature: 35.0,
        });
        chaise.passer_en_aleatoire(&mut rng);

        let mesure = chaise.mesurer(Duration::from_secs(1), &mut rng);

        assert!((mesure.poids - 90.0).abs() < 3.0);
        assert!((mesure.temperature - 35.0).abs() < 1.0);
    }
}
