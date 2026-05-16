const http = require('http')
const fs = require('fs')
const path = require('path')
const { URLSearchParams } = require('url')

const PORT = 3080
const DIR = __dirname

function parseBody(req) {
  return new Promise((resolve, reject) => {
    let data = ''
    req.on('data', chunk => { data += chunk })
    req.on('end', () => {
      try { resolve(JSON.parse(data)) }
      catch { resolve(Object.fromEntries(new URLSearchParams(data))) }
    })
    req.on('error', reject)
  })
}

const server = http.createServer(async (req, res) => {
  res.setHeader('Access-Control-Allow-Origin', '*')
  res.setHeader('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
  res.setHeader('Access-Control-Allow-Headers', 'Content-Type')

  if (req.method === 'OPTIONS') {
    res.writeHead(204)
    return res.end()
  }

  if (req.method === 'GET' && req.url === '/') {
    const html = fs.readFileSync(path.join(DIR, 'review.html'), 'utf-8')
    res.writeHead(200, { 'Content-Type': 'text/html; charset=utf-8' })
    return res.end(html)
  }

  if (req.method === 'POST' && req.url === '/feedback') {
    const body = await parseBody(req)
    const { section, comment } = body
    if (!section || !comment) {
      res.writeHead(400)
      return res.end(JSON.stringify({ error: 'need section and comment' }))
    }
    const safe = section.replace(/[^a-zA-Z0-9\u4e00-\u9fff_\-]/g, '_').slice(0, 60)
    const ts = new Date().toISOString().replace(/[:.]/g, '-').slice(0, 19)
    const filename = `feedback_${safe}_${ts}.txt`
    const content = `### ${section}\n\n${comment}\n\n---\n${new Date().toISOString()}\n`
    fs.writeFileSync(path.join(DIR, filename), content, 'utf-8')
    res.writeHead(200, { 'Content-Type': 'application/json; charset=utf-8' })
    return res.end(JSON.stringify({ ok: true, file: filename }))
  }

  if (req.method === 'GET' && req.url === '/feedback-files') {
    const files = fs.readdirSync(DIR)
      .filter(f => f.startsWith('feedback_') && f.endsWith('.txt'))
      .sort()
    res.writeHead(200, { 'Content-Type': 'application/json; charset=utf-8' })
    return res.end(JSON.stringify({ files }))
  }

  if (req.method === 'GET' && req.url.startsWith('/feedback-file/')) {
    const fname = decodeURIComponent(req.url.split('/feedback-file/')[1])
    const fpath = path.join(DIR, fname)
    if (!fs.existsSync(fpath)) {
      res.writeHead(404)
      return res.end('not found')
    }
    const content = fs.readFileSync(fpath, 'utf-8')
    res.writeHead(200, { 'Content-Type': 'text/plain; charset=utf-8' })
    return res.end(content)
  }

  res.writeHead(404)
  res.end('404')
})

server.listen(PORT, () => {
  console.log(`http://localhost:${PORT}`)
})
