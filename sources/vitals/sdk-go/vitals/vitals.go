// Package vitals reports panics and errors from Go services to Vitals (vendored by make sync-sdks).
package vitals

import (
	"bytes"
	"context"
	"crypto/rand"
	"encoding/json"
	"fmt"
	"net/http"
	"runtime"
	"strings"
	"time"
)

type config struct{ endpoint, app, version string }

var (
	cfg    *config
	queue  = make(chan map[string]any, 256)
	client = &http.Client{Timeout: 5 * time.Second}
)

// Init enables reporting; an empty endpoint disables it.
func Init(endpoint, app, version string) {
	if endpoint == "" || cfg != nil {
		return
	}
	cfg = &config{strings.TrimRight(endpoint, "/"), app, version}
	go func() {
		for ev := range queue {
			body, _ := json.Marshal(map[string]any{"events": []any{ev}})
			resp, err := client.Post(cfg.endpoint+"/v1/events", "application/json", bytes.NewReader(body))
			if err == nil {
				_ = resp.Body.Close()
			}
		}
	}()
}

func uuid() string {
	b := make([]byte, 16)
	_, _ = rand.Read(b)
	b[6] = (b[6] & 0x0f) | 0x40
	b[8] = (b[8] & 0x3f) | 0x80
	return fmt.Sprintf("%x-%x-%x-%x-%x", b[0:4], b[4:6], b[6:8], b[8:10], b[10:])
}

func frames(skip int) []map[string]any {
	pcs := make([]uintptr, 32)
	n := runtime.Callers(skip, pcs)
	it := runtime.CallersFrames(pcs[:n])
	var out []map[string]any
	for {
		f, more := it.Next()
		inApp := !strings.HasPrefix(f.Function, "runtime.") && !strings.HasPrefix(f.Function, "net/http.") &&
			!strings.Contains(f.File, "/go/pkg/mod/") && !strings.Contains(f.Function, "/vitals.")
		out = append(out, map[string]any{"function": f.Function, "file": f.File, "line": f.Line, "in_app": inApp})
		if !more {
			break
		}
	}
	// Vitals expects innermost frame last.
	for i, j := 0, len(out)-1; i < j; i, j = i+1, j-1 {
		out[i], out[j] = out[j], out[i]
	}
	return out
}

// Capture reports an error or recovered panic value.
func Capture(_ context.Context, errType string, message string, culprit string, sessionID string, skip int) {
	if cfg == nil {
		return
	}
	ev := map[string]any{
		"event_id": uuid(), "kind": "exception", "app": cfg.app, "platform": "go", "version": cfg.version,
		"ts": float64(time.Now().UnixNano()) / 1e9, "culprit": culprit,
		"error": map[string]any{"type": errType, "message": message, "frames": frames(skip)},
	}
	if sessionID != "" {
		ev["session_id"] = sessionID
	}
	select {
	case queue <- ev:
	default:
	}
}

// Middleware recovers panics, reports them, and answers 500.
func Middleware(next http.Handler) http.Handler {
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		defer func() {
			if v := recover(); v != nil {
				errType := "panic"
				if err, ok := v.(error); ok {
					errType = fmt.Sprintf("%T", err)
				}
				route := r.Pattern
				if route == "" {
					route = r.Method + " " + r.URL.Path
				}
				Capture(r.Context(), errType, fmt.Sprint(v), route, r.Header.Get("x-session-id"), 4)
				http.Error(w, `{"error":"internal error"}`, http.StatusInternalServerError)
			}
		}()
		next.ServeHTTP(w, r)
	})
}
