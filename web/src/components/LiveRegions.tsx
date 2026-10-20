/** Two live regions that are always in the page: assertive for cards and outcomes, polite for status. */
export function LiveRegions({ assertive, polite }: { assertive: string; polite: string }) {
  return (
    <div className="visually-hidden">
      <div role="alert" aria-live="assertive" aria-atomic="true" data-testid="live-assertive">
        {assertive}
      </div>
      <div role="status" aria-live="polite" aria-atomic="true" data-testid="live-polite">
        {polite}
      </div>
    </div>
  );
}
