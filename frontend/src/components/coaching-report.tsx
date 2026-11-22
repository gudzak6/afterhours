function text(value: unknown): string {
  return typeof value === "string" ? value : "";
}

function lines(value: unknown): string[] {
  return Array.isArray(value) ? value.map((item) => String(item)).filter(Boolean) : [];
}

export function CoachingReport({ report }: { report: Record<string, unknown> }) {
  if (typeof report.summary === "string" && (typeof report.activity_classification === "string" || typeof report.training_impact === "string")) {
    return <Assessment report={report} />;
  }
  if (typeof report.workout_summary === "string") {
    return <EarlierBriefing report={report} />;
  }
  return <LegacyReport report={report} />;
}

function effortLabel(value: string) {
  if (value === "Easy") return "Easy Effort";
  if (value === "Moderate") return "Moderate Effort";
  return value;
}

function paragraph(items: string[]) {
  return items.join(" ");
}

function Assessment({ report }: { report: Record<string, unknown> }) {
  const wentWell = lines(report.what_went_well);
  const focus = lines(report.where_to_focus);
  const effort = effortLabel(text(report.effort_level));
  const classification = text(report.activity_classification);

  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-center gap-2">
        {effort ? <span className="rounded-full bg-emerald-100 px-3 py-1 text-sm font-medium text-emerald-900">{effort}</span> : null}
        {classification ? <span className="rounded-full bg-emerald-100 px-3 py-1 text-sm font-medium text-emerald-900">{classification}</span> : null}
      </div>
      <Section title="Summary" body={text(report.summary)} />
      <Section title="Training Impact" body={text(report.training_impact)} />
      {wentWell.length > 0 ? (
        <div className="border-l-4 border-emerald-500 pl-4">
          <p className="font-semibold text-emerald-800">What Went Well</p>
          <p className="mt-1 leading-6">{paragraph(wentWell)}</p>
        </div>
      ) : null}
      {focus.length > 0 ? (
        <div className="border-l-4 border-amber-500 pl-4">
          <p className="font-semibold text-amber-800">What to check</p>
          <p className="mt-1 leading-6">{paragraph(focus)}</p>
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
