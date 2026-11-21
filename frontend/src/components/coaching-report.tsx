const GOAL_STATUS: Record<string, { label: string; className: string }> = {
  on_track: {
    label: "On track",
    className: "bg-emerald-100 text-emerald-900",
  },
  building: {
    label: "Building",
    className: "bg-amber-100 text-amber-950",
  },
  needs_attention: {
    label: "Needs attention",
    className: "bg-amber-200 text-amber-950",
  },
  insufficient_evidence: {
    label: "Not enough evidence",
    className: "bg-muted text-muted-foreground",
  },
};

function text(value: unknown): string {
  return typeof value === "string" ? value : "";
}

function lines(value: unknown): string[] {
  return Array.isArray(value) ? value.map((item) => String(item)).filter(Boolean) : [];
}

export function CoachingReport({ report }: { report: Record<string, unknown> }) {
  if (typeof report.summary === "string" && typeof report.activity_classification === "string") {
    return <Assessment report={report} />;
  }
  if (typeof report.workout_summary === "string") {
    return <EarlierBriefing report={report} />;
  }
  return <LegacyReport report={report} />;
}

function Assessment({ report }: { report: Record<string, unknown> }) {
  const status = GOAL_STATUS[text(report.goal_progress_status)] ?? GOAL_STATUS.insufficient_evidence;
  const wentWell = lines(report.what_went_well);
  const focus = lines(report.where_to_focus);
  const missing = lines(report.missing_information);

  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-center gap-2">
        <span className="rounded-full bg-secondary px-3 py-1 text-sm font-medium">{text(report.activity_classification)}</span>
        <span className="rounded-full border border-border px-3 py-1 text-sm">{text(report.effort_level)}</span>
      </div>
      <Section title="Summary" body={text(report.summary)} />
      <Section title="Training impact" body={text(report.training_impact)} />
      <Section title="Fitness indicators" body={text(report.fitness_indicators)} />
      {wentWell.length > 0 ? (
        <div className="rounded-xl border border-emerald-200 bg-emerald-50 px-4 py-3 text-emerald-950">
          <p className="font-medium">What went well</p>
          <ul className="mt-2 space-y-2">
            {wentWell.map((item, index) => (
              <li key={`well-${index}`}>{item}</li>
            ))}
          </ul>
        </div>
      ) : null}
      {focus.length > 0 ? (
        <div className="rounded-xl border border-amber-200 bg-amber-50 px-4 py-3 text-amber-950">
          <p className="font-medium">Where to focus</p>
          <ul className="mt-2 space-y-2">
            {focus.map((item, index) => (
              <li key={`focus-${index}`}>{item}</li>
            ))}
          </ul>
        </div>
      ) : null}
      <div>
        <div className="flex flex-wrap items-center gap-2">
          <p className="font-medium">Goal progress</p>
          <span className={`rounded-full px-2.5 py-0.5 text-xs font-medium ${status.className}`}>{status.label}</span>
        </div>
        <p className="mt-1 whitespace-pre-wrap">{text(report.goal_progress)}</p>
      </div>
      {missing.length > 0 ? (
        <div>
          <p className="font-medium">Missing information</p>
          <ul className="mt-1 list-disc space-y-1 pl-5 text-muted-foreground">
            {missing.map((item, index) => (
              <li key={`missing-${index}`}>{item}</li>
            ))}
          </ul>
        </div>
      ) : null}
    </div>
  );
}

function Section({ title, body }: { title: string; body: string }) {
  if (!body) {
    return null;
  }
  return (
    <div>
      <p className="font-medium">{title}</p>
      <p className="mt-1 whitespace-pre-wrap">{body}</p>
    </div>
  );
}

function EarlierBriefing({ report }: { report: Record<string, unknown> }) {
  return (
    <div className="space-y-4">
      <Section title="Workout summary" body={text(report.workout_summary)} />
      <Section title="Execution" body={text(report.execution_analysis)} />
      <Section title="Physiological interpretation" body={text(report.physiological_interpretation)} />
      <Section title="Historical context" body={text(report.historical_context)} />
      <Section title="Fatigue and recovery" body={text(report.fatigue_recovery)} />
      <Section title="Daily summary" body={text(report.coach_daily_summary)} />
    </div>
  );
}

function LegacyReport({ report }: { report: Record<string, unknown> }) {
  const interpretation = report.interpretation;
  return (
    <div className="space-y-3">
      <BulletList title="Measured facts" items={lines(report.measured_facts)} />
      <BulletList title="Calculated metrics" items={lines(report.calculated_metrics)} />
      {Array.isArray(interpretation) ? <BulletList title="Interpretation" items={lines(interpretation)} /> : null}
      {typeof interpretation === "string" ? <Section title="Interpretation" body={interpretation} /> : null}
      <BulletList title="Recommendations" items={lines(report.recommendations)} />
    </div>
  );
}

function BulletList({ title, items }: { title: string; items: string[] }) {
  if (items.length === 0) {
    return null;
  }
  return (
    <div>
      <p className="font-medium">{title}</p>
      <ul className="mt-1 list-disc space-y-1 pl-5">
        {items.map((item, index) => (
          <li key={`${title}-${index}`}>{item}</li>
        ))}
      </ul>
    </div>
  );
}
