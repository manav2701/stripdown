import express from 'express';
import { boolVariation } from './flags';
const app = express();

app.get('/api/invoices', async (req, res) => {
  if (!(await boolVariation('legacy-invoice-export', req.user))) return res.sendStatus(404);
  res.json([]);
});
app.post('/api/reports/export', (req, res) => res.json({}));
app.post('/api/webhooks/stripe', (req, res) => res.sendStatus(200));

const plan = req.user.plan;
if (plan === 'enterprise') { /* sso */ }
