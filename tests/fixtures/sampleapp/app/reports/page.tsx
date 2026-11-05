import posthog from 'posthog-js';
import { useFlags } from 'launchdarkly-react-client-sdk';

export default function ReportsPage() {
  const flags = useFlags();
  if (!flags.advancedReports) return null;
  posthog.capture('report_viewed');
  return <div>reports</div>;
}
