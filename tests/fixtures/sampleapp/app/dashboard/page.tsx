import posthog from 'posthog-js';
export default function Dashboard() {
  posthog.capture('dashboard_viewed');
  return <div>dash</div>;
}
