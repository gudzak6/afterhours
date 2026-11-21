export function isTestAthlete(name: string) {
  return name.trim().toLowerCase().startsWith("riley");
}

export function AthleteName({ name }: { name: string }) {
  return (
    <span>
      {name}
      {isTestAthlete(name) ? (
        <span className="ml-1.5 align-middle text-[0.72em] font-normal italic tracking-normal text-muted-foreground">test data</span>
      ) : null}
    </span>
  );
}
