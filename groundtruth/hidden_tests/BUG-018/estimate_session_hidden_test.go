// Hidden test for BUG-018 (never committed to the target repo). Copied to payments/ at eval time.
package main

import (
	"encoding/json"
	"net/http"
	"testing"
)

func TestEstimateWithSessionHidden(t *testing.T) {
	h := NewServer().Routes()
	body := map[string]any{"city": "sf", "distance_km": 10, "duration_min": 20, "session_id": "s-hidden"}
	var amounts []float64
	for i := 0; i < 2; i++ { // the gateway always sends a session id; the second call may be served from a cache
		rec := post(t, h, "/fares/estimate", body)
		if rec.Code != http.StatusOK {
			t.Fatalf("call %d: status %d: %s", i+1, rec.Code, rec.Body)
		}
		var q map[string]any
		_ = json.Unmarshal(rec.Body.Bytes(), &q)
		amounts = append(amounts, q["amount_cents"].(float64))
	}
	if amounts[0] != 2295 || amounts[1] != amounts[0] {
		t.Fatalf("unexpected amounts %v", amounts)
	}
}
