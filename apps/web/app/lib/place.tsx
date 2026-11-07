"use client";
// Where the dashboard works: the workspace (sent as X-Workspace) and the portfolio in it.
// Priority for each: saved choice > the API's default > the first one listed.
import { createContext, Fragment, useContext, useEffect, useState, type ReactNode } from "react";
import { api, setApiWorkspace } from "./api";

// used when the API cannot list portfolios (offline, or an API older than /portfolios)
const FALLBACK_PORTFOLIO = "PORTFOLIO#2026-Q1";
const WORKSPACE_KEY = "ma-pmo-workspace";
const portfolioKey = (workspace: string) => `ma-pmo-portfolio:${workspace}`;

type Workspace = { id: string; name: string; roles: string[] };
type Portfolio = { id: string; name: string; period: string };
type Ctx = {
  workspaces: Workspace[];
  workspace: string;
  setWorkspace: (id: string) => void;
  portfolios: Portfolio[];
  portfolio: string;
  setPortfolio: (id: string) => void;
};
const PlaceContext = createContext<Ctx>({
  workspaces: [], workspace: "", setWorkspace: () => {},
  portfolios: [], portfolio: FALLBACK_PORTFOLIO, setPortfolio: () => {},
});

function load(key: string): string | null {
  try {
    return window.localStorage.getItem(key);
  } catch {
    return null; // storage may be blocked (private mode)
  }
}

function save(key: string, value: string) {
  try {
    window.localStorage.setItem(key, value);
  } catch {
    // ignore
  }
}

function pick<T extends { id: string }>(items: T[], ...wanted: (string | null | undefined)[]) {
  for (const id of wanted) if (id && items.some((i) => i.id === id)) return id;
  return items[0]?.id;
}

export function PlaceProvider({ children }: { children: ReactNode }) {
  const [workspaces, setWorkspaces] = useState<Workspace[]>([]);
  const [workspace, setWorkspaceState] = useState("");
  const [portfolios, setPortfolios] = useState<Portfolio[]>([]);
  const [portfolio, setPortfolioState] = useState(FALLBACK_PORTFOLIO);
  const [ready, setReady] = useState(false);

  // switch workspace and portfolio together, so no page asks for one workspace's portfolio in another
  async function enter(id: string) {
    setApiWorkspace(id);
    let listed: Portfolio[] = [];
    let chosen = FALLBACK_PORTFOLIO;
    try {
      const found = await api.portfolios();
      listed = found.portfolios;
      chosen = pick(listed, load(portfolioKey(id)), found.default) ?? found.default;
    } catch {
      // keep the fallback portfolio
    }
    setWorkspaceState(id);
    setPortfolios(listed);
    setPortfolioState(chosen);
  }

  useEffect(() => {
    (async () => {
      try {
        const listed = await api.workspaces();
        setWorkspaces(listed.workspaces);
        const id = pick(listed.workspaces, load(WORKSPACE_KEY), listed.default);
        if (id) await enter(id);
      } catch {
        // offline or an older API: no switcher, the API's own default workspace
      }
      setReady(true);
    })();
  }, []);

  const setWorkspace = (id: string) => {
    save(WORKSPACE_KEY, id);
    enter(id);
  };
  const setPortfolio = (id: string) => {
    save(portfolioKey(workspace), id);
    setPortfolioState(id);
  };

  // Render only once the place is known, and remount on a change so every page refetches.
  return (
    <PlaceContext.Provider value={{ workspaces, workspace, setWorkspace, portfolios, portfolio, setPortfolio }}>
      {ready ? <Fragment key={`${workspace}|${portfolio}`}>{children}</Fragment> : null}
    </PlaceContext.Provider>
  );
}

export function usePlace() {
  return useContext(PlaceContext);
}
