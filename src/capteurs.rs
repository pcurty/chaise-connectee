use rand::{Rng, RngExt};

use crate::bruit::{BruitCapteur, arrondir};

#[derive(Debug, Clone, Copy, PartialEq)]
pub struct Occupant {
    pub poids_kg: f64,
}

#[derive(Debug, Clone, PartialEq)]
pub struct EtatPhysique {
    pub occupant: Option<Occupant>,
    pub temperature_assise: f64,
}

pub trait Capteur {
    type Mesure;

    fn lire<R: Rng>(&mut self, etat: &EtatPhysique, rng: &mut R) -> Self::Mesure;
}

#[derive(Debug, Clone)]
pub struct CapteurPresence {
    probabilite_erreur: f64,
    etat_stable: bool,
    changement_en_attente: bool,
}

impl CapteurPresence {
    pub fn new(probabilite_erreur: f64) -> Self {
        Self {
            probabilite_erreur: probabilite_erreur.clamp(0.0, 1.0),
            etat_stable: false,
            changement_en_attente: false,
        }
    }
}

impl Capteur for CapteurPresence {
    type Mesure = bool;

    fn lire<R: Rng>(&mut self, etat: &EtatPhysique, rng: &mut R) -> bool {
        let erreur = rng.random_bool(self.probabilite_erreur);
        let lecture = etat.occupant.is_some() != erreur;

        if lecture == self.etat_stable {
            self.changement_en_attente = false;
        } else if self.changement_en_attente {
            self.etat_stable = lecture;
            self.changement_en_attente = false;
        } else {
            self.changement_en_attente = true;
        }
        self.etat_stable
    }
}

#[derive(Debug, Clone)]
pub struct CapteurPoids {
    bruit: BruitCapteur,
}

impl CapteurPoids {
    pub fn new() -> Self {
        Self {
            bruit: BruitCapteur::new(0.15, 0.01, 0.3),
        }
    }
}

impl Capteur for CapteurPoids {
    type Mesure = f64;

    fn lire<R: Rng>(&mut self, etat: &EtatPhysique, rng: &mut R) -> f64 {
        let charge = match etat.occupant {
            Some(occupant) => occupant.poids_kg + rng.random_range(-0.6..=0.6),
            None => 0.0,
        };
        arrondir(self.bruit.appliquer(charge, rng).max(0.0), 2)
    }
}

#[derive(Debug, Clone)]
pub struct CapteurTemperature {
    bruit: BruitCapteur,
}

impl CapteurTemperature {
    pub fn new() -> Self {
        Self {
            bruit: BruitCapteur::new(0.05, 0.005, 0.2),
        }
    }
}

impl Capteur for CapteurTemperature {
    type Mesure = f64;

    fn lire<R: Rng>(&mut self, etat: &EtatPhysique, rng: &mut R) -> f64 {
        arrondir(self.bruit.appliquer(etat.temperature_assise, rng), 2)
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use rand::SeedableRng;
    use rand::rngs::StdRng;

    fn etat(occupant: Option<Occupant>) -> EtatPhysique {
        EtatPhysique {
            occupant,
            temperature_assise: 21.0,
        }
    }

    #[test]
    fn la_presence_exige_deux_lectures_concordantes() {
        let mut rng = StdRng::seed_from_u64(1);
        let mut capteur = CapteurPresence::new(0.0);
        let occupe = etat(Some(Occupant { poids_kg: 70.0 }));

        assert!(!capteur.lire(&occupe, &mut rng));
        assert!(capteur.lire(&occupe, &mut rng));
    }

    #[test]
    fn le_poids_a_vide_n_est_jamais_negatif() {
        let mut rng = StdRng::seed_from_u64(2);
        let mut capteur = CapteurPoids::new();
        for _ in 0..1_000 {
            assert!(capteur.lire(&etat(None), &mut rng) >= 0.0);
        }
    }
}
