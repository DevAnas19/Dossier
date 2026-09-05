// Set VITE_API_URL in a .env file when deploying (e.g. VITE_API_URL=https://your-backend.up.railway.app)
const API_BASE = import.meta.env.VITE_API_URL || 'http://localhost:8000'

export async function startResearch(topic) {
  const res = await fetch(`${API_BASE}/api/research`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ topic }),
  })
  if (!res.ok) {
    const err = await res.json().catch(() => ({}))
    throw new Error(err.detail || 'Failed to start research')
  }
  return res.json()
}

export async function getResearchStatus(jobId) {
  const res = await fetch(`${API_BASE}/api/research/${jobId}`)
  if (!res.ok) throw new Error('Failed to fetch job status')
  return res.json()
}
