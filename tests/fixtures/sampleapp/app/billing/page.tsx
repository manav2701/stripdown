import posthog from 'posthog-js';

export default function BillingPage() {
  const onCheckout = () => {
    posthog.capture('checkout_started', { source: 'billing' });
  };
  const onInvoice = () => {
    posthog.capture('invoice_downloaded');
  };
  return <button onClick={onCheckout}>Upgrade</button>;
}
