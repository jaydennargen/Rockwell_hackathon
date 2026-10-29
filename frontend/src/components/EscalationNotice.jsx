import Section from "./Section.jsx";

export default function EscalationNotice({ escalation }) {
  return (
    <Section title="Why it's with a specialist" tone="review">
      <p className="lead">{escalation.message}</p>
      {escalation.reasons?.length > 0 && (
        <ul className="plain-list">
          {escalation.reasons.map((r) => (
            <li key={r}>{r}</li>
          ))}
        </ul>
      )}
    </Section>
  );
}
