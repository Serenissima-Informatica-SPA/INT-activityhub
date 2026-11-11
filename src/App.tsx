import { useState } from "react";
import ActivityCalendarPage from "./ActivityCalendarPage";
import GroupAnalysisPage from "./GroupAnalysisPage";
import JobProgressPage from "./JobProgressPage";
import type { Task } from "./types";
import "./App.css";

type PageId = "activity-calendar" | "group-analysis" | "job-progress";
const PAGE_ITEMS: { id: PageId; label: string }[] = [
  { id: "activity-calendar", label: "Monitor risorse" },
  { id: "group-analysis", label: "Monitor gruppi" },
  { id: "job-progress", label: "Avanzamento commesse" },
];

export default function App() {
  const [page, setPage] = useState<PageId>("activity-calendar");
  const tasks: Task[] = [];

  return (
    <>
      <nav className="activity-hub-nav" aria-label="Pagine principali">
        {PAGE_ITEMS.map((item) => (
          <button
            key={item.id}
            type="button"
            className={page === item.id ? "active" : ""}
            aria-current={page === item.id ? "page" : undefined}
            onClick={() => setPage(item.id)}
          >
            {item.label}
          </button>
        ))}
      </nav>
      {page === "activity-calendar" ? (
        <ActivityCalendarPage />
      ) : page === "group-analysis" ? (
        <GroupAnalysisPage />
      ) : (
        <JobProgressPage
          tasks={tasks}
          onSwitchPage={() => setPage("activity-calendar")}
        />
      )}
    </>
  );
}
