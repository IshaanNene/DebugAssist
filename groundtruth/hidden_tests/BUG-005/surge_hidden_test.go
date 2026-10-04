// Hidden test for BUG-005 (never committed to the target repo). Copied to payments/ at eval time.
package main

import (
	"testing"
	"time"
)

func TestFreshServerSurgeCacheIsUsable(t *testing.T) {
	s := NewServer()
	defer func() {
		if r := recover(); r != nil {
			t.Fatalf("surge cache panicked: %v", r)
		}
	}()
	if m := s.surge.get("nyc", time.Now(), demandMultiplier); m < 1 {
		t.Fatalf("bad multiplier %v", m)
	}
}
