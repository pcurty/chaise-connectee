use rand::{Rng, RngExt};
use rand_distr::StandardNormal;

#[derive(Debug, Clone)]
pub struct BruitCapteur {
    ecart_type: f64,
    pas_derive: f64,
    derive_max: f64,
    derive: f64,
}

impl BruitCapteur {
    pub fn new(ecart_type: f64, pas_derive: f64, derive_max: f64) -> Self {
        Self {
            ecart_type,
            pas_derive,
            derive_max,
            derive: 0.0,
        }
    }

    pub fn appliquer<R: Rng>(&mut self, valeur: f64, rng: &mut R) -> f64 {
        let pas: f64 = rng.sample(StandardNormal);
        self.derive =
            (self.derive + pas * self.pas_derive).clamp(-self.derive_max, self.derive_max);

        let bruit: f64 = rng.sample(StandardNormal);
        valeur + self.derive + bruit * self.ecart_type
    }
}

pub fn arrondir(valeur: f64, decimales: i32) -> f64 {
    let facteur = 10_f64.powi(decimales);
    (valeur * facteur).round() / facteur
}

#[cfg(test)]
mod tests {
    use super::*;
    use rand::SeedableRng;
    use rand::rngs::StdRng;

    #[test]
    fn la_derive_reste_bornee() {
        let mut rng = StdRng::seed_from_u64(42);
        let mut bruit = BruitCapteur::new(0.0, 1.0, 0.5);
        for _ in 0..1_000 {
            assert!(bruit.appliquer(10.0, &mut rng).abs() <= 10.5);
        }
    }

    #[test]
    fn arrondit_a_deux_decimales() {
        assert_eq!(arrondir(21.456, 2), 21.46);
    }
}
