from debugassist.llm.outline import outline

TS = """import { x } from "y";

export function httpBackends(url: string): Backends {
  return {
    async eta(rideId) {
      const r = await call<Eta>(url);
      if (r.status === 404) throw err;
      return r.body;
    },
  };
}

export const parseOrigins = (raw: string) => raw.split(",");
class Poller {
  tick() {
    for (const x of y) {
    }
  }
}
"""

PY = """import os


class Driver:
    def busy(self) -> bool:
        return False


async def nearest_available_driver(session, city):
    if city:
        pass
"""

GO = """package main

type Server struct {
	recent map[string]int
}

func NewServer() *Server {
	return &Server{}
}

func (s *Server) quote(w http.ResponseWriter) {
}
"""


def test_typescript_symbols_with_line_numbers() -> None:
    out = outline("gateway/src/backends.ts", TS)
    assert "3  export function httpBackends" in out
    assert "5      async eta(rideId)" in out
    assert "13  export const parseOrigins" in out
    assert "14  class Poller" in out and "15    tick()" in out
    assert "for (const" not in out  # control flow is not a symbol


def test_python_and_go() -> None:
    py = outline("dispatch/matching.py", PY)
    assert (
        "4  class Driver" in py and "5      def busy" in py and "9  async def nearest_available_driver" in py
    )
    go = outline("payments/main.go", GO)
    assert (
        "3  type Server struct" in go and "7  func NewServer()" in go and "11  func (s *Server) quote" in go
    )


def test_reports_size_and_falls_back() -> None:
    assert outline("README.md", "# Title\ntext\n").startswith("README.md: 2 lines, 0 symbols")


def test_const_values_are_not_functions() -> None:
    out = outline(
        "a.ts",
        "export const f = (x: number) => x;\nconst body = (text ? JSON.parse(text) : null);\nconst g = async (a) => a;\n",
    )
    assert "1  export const f" in out and "3  const g" in out and "const body" not in out
