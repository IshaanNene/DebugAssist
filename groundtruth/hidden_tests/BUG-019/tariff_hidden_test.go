// Hidden test for BUG-019 (never committed to the target repo). Copied to payments/internal/fares/ at eval time.
package fares

import "testing"

// Per-km prices must stay in a plausible band for each market (minor units per km).
func TestPerKmPricesArePlausibleHidden(t *testing.T) {
	bands := map[string][2]int64{"sf": {50, 300}, "nyc": {50, 300}, "blr": {800, 2500}, "tokyo": {150, 600}}
	for city, band := range bands {
		short, _ := Estimate(city, 20, 0, 1)
		long, _ := Estimate(city, 30, 0, 1)
		perKm := (long.AmountCents - short.AmountCents) / 10
		if perKm < band[0] || perKm > band[1] {
			t.Errorf("%s: %d minor units per km is outside %v", city, perKm, band)
		}
	}
}
