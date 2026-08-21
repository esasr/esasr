#!/usr/bin/env node

import { randomBytes } from 'node:crypto'
import { spawn, spawnSync } from 'node:child_process'
import {
  access,
  chmod,
  copyFile,
  cp,
  mkdir,
  readFile,
  readdir,
  stat,
  writeFile,
} from 'node:fs/promises'
import { constants } from 'node:fs'
import { createServer } from 'node:net'
import { dirname, extname, join, relative, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'
import { emitKeypressEvents } from 'node:readline'
import { createInterface } from 'node:readline/promises'
import { setTimeout as delay } from 'node:timers/promises'

const PACKAGE_ROOT = resolve(dirname(fileURLToPath(import.meta.url)), '..')
const PROVIDERS = {
  deepseek: { label: 'DeepSeek', key: 'DEEPSEEK_API_KEY' },
  qwen: { label: '通义千问（Qwen）', key: 'QWEN_API_KEY' },
  openai: { label: 'OpenAI', key: 'OPENAI_API_KEY' },
  kimi: { label: 'Kimi / Moonshot', key: 'KIMI_API_KEY' },
  custom: { label: '兼容 OpenAI API 的自定义平台', key: 'CUSTOM_LLM_API_KEY' },
}
const PROJECT_FILES = [
  'bin',
  'scripts',
  'scholarseeker-api',
  'scholarseeker-web',
  '.env.example',
  '.gitignore',
  '.npmignore',
  'config_example.yaml',
  'docker-compose.yml',
  'package.json',
  'README.md',
  'run.sh',
  'LICENSE',
]
const EXCLUDED_DIRECTORIES = new Set([
  '.git', '__pycache__', 'dist', 'node_modules', 'venv', 'work', 'outputs',
])

function includeProjectFile(source) {
  const path = relative(PACKAGE_ROOT, source)
  const parts = path.split(/[\\/]/)
  if (parts.some((part) => EXCLUDED_DIRECTORIES.has(part))) return false
  const name = parts.at(-1)
  if (name === '.env' || name === 'config.yaml' || name === '.DS_Store') return false
  return extname(name) !== '.db' && extname(name) !== '.pyc'
}

function printHelp() {
  console.log(`ScholarSeeker CLI

用法：
  scholarseeker init [目录]   创建项目并引导配置 API Key
  scholarseeker setup         重新运行配置向导
  scholarseeker doctor        检查 Docker 和配置
  scholarseeker start [...]   启动服务，可传 --no-build/--pull/--with-reranker
  scholarseeker stop          停止服务
  scholarseeker status        查看服务状态
  scholarseeker logs [...]    查看日志
  scholarseeker --help        显示帮助`)
}

function characterWidth(character) {
  if (/\p{Mark}/u.test(character)) return 0
  const codePoint = character.codePointAt(0)
  if (
    codePoint >= 0x1100 && (
      codePoint <= 0x115f || codePoint === 0x2329 || codePoint === 0x232a ||
      (codePoint >= 0x2e80 && codePoint <= 0xa4cf && codePoint !== 0x303f) ||
      (codePoint >= 0xac00 && codePoint <= 0xd7a3) ||
      (codePoint >= 0xf900 && codePoint <= 0xfaff) ||
      (codePoint >= 0xfe10 && codePoint <= 0xfe19) ||
      (codePoint >= 0xfe30 && codePoint <= 0xfe6f) ||
      (codePoint >= 0xff00 && codePoint <= 0xff60) ||
      (codePoint >= 0xffe0 && codePoint <= 0xffe6) ||
      (codePoint >= 0x1f300 && codePoint <= 0x1faff)
    )
  ) return 2
  return 1
}

function displayWidth(value) {
  return Array.from(value).reduce((width, character) => width + characterWidth(character), 0)
}

function wrapByDisplayWidth(value, maximumWidth) {
  const lines = []
  let line = ''
  let width = 0
  for (const character of Array.from(value)) {
    const nextWidth = characterWidth(character)
    if (line && width + nextWidth > maximumWidth) {
      lines.push(line)
      line = ''
      width = 0
    }
    line += character
    width += nextWidth
  }
  if (line) lines.push(line)
  return lines
}

function printBanner() {
  const title = '第八届中国研究生人工智能创新大赛企业赛题-科研场景下复杂学术查询的智能论文搜索与推荐演示项目'
  const terminalWidth = process.stdout.columns || 80
  const contentWidth = Math.max(10, Math.min(72, terminalWidth - 4))
  const border = '═'.repeat(contentWidth + 2)
  const lines = wrapByDisplayWidth(title, contentWidth)
  console.log(`\n╔${border}╗`)
  for (const line of lines) {
    const padding = ' '.repeat(contentWidth - displayWidth(line))
    console.log(`║ ${line}${padding} ║`)
  }
  console.log(`╚${border}╝\n`)
}

async function exists(path) {
  try {
    await access(path, constants.F_OK)
    return true
  } catch {
    return false
  }
}

async function isEmptyDirectory(path) {
  if (!(await exists(path))) return true
  return (await readdir(path)).length === 0
}

async function findProjectRoot(start = process.cwd()) {
  let current = resolve(start)
  while (true) {
    if (
      (await exists(join(current, 'docker-compose.yml'))) &&
      (await exists(join(current, '.env.example')))
    ) return current
    const parent = dirname(current)
    if (parent === current) return null
    current = parent
  }
}

async function ask(question, defaultValue = '') {
  const rl = createInterface({ input: process.stdin, output: process.stdout })
  const suffix = defaultValue ? ` [${defaultValue}]` : ''
  const answer = (await rl.question(`${question}${suffix}: `)).trim()
  rl.close()
  return answer || defaultValue
}

async function askYesNo(question, defaultYes = true) {
  const answer = (await ask(`${question} (${defaultYes ? 'Y/n' : 'y/N'})`)).toLowerCase()
  if (!answer) return defaultYes
  return answer === 'y' || answer === 'yes' || answer === '是'
}

async function askSecret(question) {
  if (!process.stdin.isTTY || !process.stdin.setRawMode) {
    return ask(question)
  }
  process.stdout.write(`${question}（输入内容不会显示）: `)
  process.stdin.setRawMode(true)
  process.stdin.resume()
  process.stdin.setEncoding('utf8')
  return new Promise((resolveSecret, reject) => {
    let value = ''
    const cleanup = () => {
      process.stdin.setRawMode(false)
      process.stdin.pause()
      process.stdin.removeListener('data', onData)
      process.stdout.write('\n')
    }
    let finished = false
    const onData = (data) => {
      for (const char of data) {
        if (finished) return
        if (char === '\u0003') {
          finished = true
          cleanup()
          reject(new Error('已取消配置'))
        } else if (char === '\r' || char === '\n') {
          finished = true
          cleanup()
          resolveSecret(value.trim())
        } else if (char === '\u007f' || char === '\b') {
          value = value.slice(0, -1)
        } else if (char >= ' ') {
          value += char
        }
      }
    }
    process.stdin.on('data', onData)
  })
}

function parseEnv(content) {
  const values = new Map()
  for (const line of content.split(/\r?\n/)) {
    const match = line.match(/^([A-Z][A-Z0-9_]*)=(.*)$/)
    if (match) values.set(match[1], match[2])
  }
  return values
}

function updateEnv(content, updates) {
  const remaining = new Map(Object.entries(updates))
  const lines = content.split(/\r?\n/).map((line) => {
    const match = line.match(/^([A-Z][A-Z0-9_]*)=/)
    if (!match || !remaining.has(match[1])) return line
    const value = remaining.get(match[1])
    remaining.delete(match[1])
    return `${match[1]}=${value}`
  })
  for (const [key, value] of remaining) lines.push(`${key}=${value}`)
  return `${lines.join('\n').replace(/\n+$/, '')}\n`
}

async function ensureLocalConfig(root) {
  const envPath = join(root, '.env')
  const configPath = join(root, 'config.yaml')
  if (!(await exists(envPath))) await copyFile(join(root, '.env.example'), envPath)
  if (!(await exists(configPath))) {
    await copyFile(join(root, 'config_example.yaml'), configPath)
  }
  return envPath
}

async function chooseProvider() {
  const names = Object.keys(PROVIDERS)
  if (!process.stdin.isTTY || !process.stdin.setRawMode) {
    console.log('\n请选择查询规划使用的大模型平台：')
    names.forEach((name, index) => console.log(`  ${index + 1}. ${PROVIDERS[name].label}`))
    const choice = await ask('输入序号', '1')
    const index = Number(choice) - 1
    if (!Number.isInteger(index) || index < 0 || index >= names.length) {
      throw new Error('无效的平台序号')
    }
    return names[index]
  }

  console.log('\n请选择查询规划使用的大模型平台：')
  let selected = 0
  let rendered = false
  const lineCount = names.length + 1
  const draw = () => {
    if (rendered) process.stdout.write(`\x1b[${lineCount}A`)
    names.forEach((name, index) => {
      const active = index === selected
      process.stdout.write(`\x1b[2K\r${active ? '❯ ◉' : '  ○'} ${PROVIDERS[name].label}\n`)
    })
    process.stdout.write('\x1b[2K\r↑/↓ 移动 · 空格选择')
    rendered = true
  }

  emitKeypressEvents(process.stdin)
  process.stdin.setRawMode(true)
  process.stdin.resume()
  process.stdout.write('\x1b[?25l')
  draw()
  return new Promise((resolveProvider, reject) => {
    const cleanup = () => {
      process.stdin.removeListener('keypress', onKeypress)
      process.stdin.setRawMode(false)
      process.stdin.pause()
      process.stdout.write('\x1b[?25h\n')
    }
    const onKeypress = (input, key = {}) => {
      if (key.ctrl && key.name === 'c') {
        cleanup()
        reject(new Error('已取消配置'))
      } else if (key.name === 'up') {
        selected = (selected - 1 + names.length) % names.length
        draw()
      } else if (key.name === 'down') {
        selected = (selected + 1) % names.length
        draw()
      } else if (input === ' ' || key.name === 'return') {
        const provider = names[selected]
        cleanup()
        resolveProvider(provider)
      }
    }
    process.stdin.on('keypress', onKeypress)
  })
}

async function setupProject(root) {
  const envPath = await ensureLocalConfig(root)
  const original = await readFile(envPath, 'utf8')
  const current = parseEnv(original)
  const provider = await chooseProvider()
  const providerConfig = PROVIDERS[provider]
  console.log(`\n请从 ${providerConfig.label} 官方控制台创建 API Key。`)
  const suppliedKey = process.env.SCHOLARSEEKER_API_KEY || await askSecret('API Key')
  if (!suppliedKey) throw new Error('API Key 不能为空')

  const updates = {
    LLM_ACTIVE_PROVIDER: provider,
    [providerConfig.key]: suppliedKey,
  }
  if (provider === 'custom') {
    updates.CUSTOM_LLM_BASE_URL = await ask(
      'API Base URL',
      current.get('CUSTOM_LLM_BASE_URL') || 'https://api.example.com/v1',
    )
    updates.CUSTOM_LLM_MODEL = await ask(
      '模型名称',
      current.get('CUSTOM_LLM_MODEL') || 'gpt-4o-mini',
    )
  }
  if (!current.get('JWT_SECRET') || current.get('JWT_SECRET') === 'change_me_to_a_long_random_string') {
    updates.JWT_SECRET = randomBytes(32).toString('hex')
  }

  if (await askYesNo('\n是否配置可选的学术数据源凭据', false)) {
    const semanticKey = await askSecret('Semantic Scholar API Key（可直接回车跳过）')
    if (semanticKey) updates.SEMANTIC_SCHOLAR_API_KEY = semanticKey
    const openAlexKey = await askSecret('OpenAlex API Key（可直接回车跳过）')
    if (openAlexKey) updates.OPENALEX_API_KEY = openAlexKey
    const openAlexEmail = await ask('OpenAlex 联系邮箱（可直接回车跳过）')
    if (openAlexEmail) updates.OPENALEX_EMAIL = openAlexEmail
  }

  await writeFile(envPath, updateEnv(original, updates), { mode: 0o600 })
  await chmod(envPath, 0o600)
  console.log(`\n✓ 配置已保存到 ${envPath}`)
  console.log('  API Key 只保存在本机 .env，不会写入前端或提交到 Git。')
}

async function initProject(destinationArg) {
  const destination = resolve(destinationArg || 'scholarseeker')
  if (!(await isEmptyDirectory(destination))) {
    throw new Error(`目标目录不是空目录：${destination}`)
  }
  if (destination === PACKAGE_ROOT) throw new Error('不能覆盖 npm 包自身目录')
  await mkdir(destination, { recursive: true })
  for (const file of PROJECT_FILES) {
    const source = join(PACKAGE_ROOT, file)
    if (!(await exists(source))) continue
    const target = join(destination, file)
    const metadata = await stat(source)
    if (metadata.isDirectory()) {
      await cp(source, target, { recursive: true, filter: includeProjectFile })
    }
    else await copyFile(source, target)
  }
  const gitignoreTemplate = join(PACKAGE_ROOT, 'templates', 'gitignore')
  if (await exists(gitignoreTemplate)) {
    await copyFile(gitignoreTemplate, join(destination, '.gitignore'))
  }
  console.log(`✓ ScholarSeeker 已创建：${destination}`)
  if (process.stdin.isTTY) await setupProject(destination)
  else console.log(`下一步：cd ${destination} && scholarseeker setup`)
  console.log(`\n启动：cd ${destination} && scholarseeker start`)
}

function commandWorks(command, args) {
  return spawnSync(command, args, { stdio: 'ignore' }).status === 0
}

function startupAnimationEnabled() {
  return process.stdout.isTTY || process.env.SCHOLARSEEKER_FORCE_ANIMATION === '1'
}

function startupCardLine(value, width) {
  const visibleValue = value.replace(/\x1b\[[0-9;]*m/g, '')
  const padding = ' '.repeat(Math.max(0, width - displayWidth(visibleValue)))
  return `\x1b[2m│\x1b[22m ${value}${padding} \x1b[2m│\x1b[0m`
}

function printStartupCard() {
  const terminalWidth = process.stdout.columns || 80
  const contentWidth = Math.max(28, Math.min(56, terminalWidth - 4))
  const border = '─'.repeat(contentWidth + 2)
  console.log(`\x1b[2m╭${border}╮\x1b[0m`)
  console.log(startupCardLine('\x1b[1;36m>_ ScholarSeeker\x1b[0m', contentWidth))
  console.log(startupCardLine('', contentWidth))
  console.log(startupCardLine('Intelligent academic search · starting services', contentWidth))
  console.log(`\x1b[2m╰${border}╯\x1b[0m`)
}

function shimmer(value, frame) {
  const characters = Array.from(value)
  const head = frame % (characters.length + 8)
  return characters.map((character, index) => {
    const distance = head - index
    if (distance === 0) return `\x1b[1;96m${character}\x1b[0m`
    if (distance > 0 && distance <= 3) return `\x1b[36m${character}\x1b[0m`
    return `\x1b[2m${character}\x1b[0m`
  }).join('')
}

function isPortAvailable(port) {
  return new Promise((resolveAvailable) => {
    const server = createServer()
    server.unref()
    server.once('error', () => resolveAvailable(false))
    server.listen({ host: '0.0.0.0', port, exclusive: true }, () => {
      server.close(() => resolveAvailable(true))
    })
  })
}

function composeOwnsPort(root, service, containerPort, hostPort) {
  const result = spawnSync(
    'docker',
    ['compose', 'port', service, String(containerPort)],
    { cwd: root, encoding: 'utf8', stdio: ['ignore', 'pipe', 'ignore'] },
  )
  if (result.status !== 0) return false
  const published = result.stdout.trim().split(':').at(-1)
  return Number(published) === hostPort
}

async function nextAvailablePort(start, reserved) {
  for (let port = start; port < start + 100; port += 1) {
    if (!reserved.has(port) && await isPortAvailable(port)) return port
  }
  throw new Error(`无法在 ${start}-${start + 99} 范围内找到空闲端口`)
}

async function resolvePortConflicts(root) {
  const envPath = join(root, '.env')
  const original = await readFile(envPath, 'utf8')
  const current = parseEnv(original)
  const bindings = [
    ['WEB_PORT', 8080, 'Web', 'web', 80],
    ['API_PORT', 8000, 'API', 'api', 8000],
    ['POSTGRES_PORT', 5432, 'PostgreSQL', 'postgres', 5432],
    ['REDIS_PORT', 6379, 'Redis', 'redis', 6379],
    ['NEO4J_HTTP_PORT', 7474, 'Neo4j HTTP', 'neo4j', 7474],
    ['NEO4J_BOLT_PORT', 7687, 'Neo4j Bolt', 'neo4j', 7687],
  ]
  const reserved = new Set(
    bindings.map(([key, fallback]) => Number(current.get(key) || fallback)),
  )
  const updates = {}

  for (const [key, fallback, label, service, containerPort] of bindings) {
    const requested = Number(current.get(key) || fallback)
    if (!Number.isInteger(requested) || requested < 1 || requested > 65535) {
      throw new Error(`${key}=${current.get(key)} 不是有效端口`)
    }
    if (
      await isPortAvailable(requested) ||
      composeOwnsPort(root, service, containerPort, requested)
    ) continue

    reserved.delete(requested)
    const replacement = await nextAvailablePort(requested + 1, reserved)
    reserved.add(replacement)
    updates[key] = String(replacement)
    console.log(`⚠ ${label} 端口 ${requested} 已被占用，自动改用 ${replacement}`)
  }

  if (Object.keys(updates).length) {
    await writeFile(envPath, updateEnv(original, updates), { mode: 0o600 })
    await chmod(envPath, 0o600)
    console.log('✓ 新端口已保存到 .env')
  }
}

async function ensureDockerReady() {
  if (!commandWorks('docker', ['--version'])) {
    throw new Error('未安装 Docker。请先安装并启动 Docker Desktop：https://www.docker.com/products/docker-desktop/')
  }
  if (!commandWorks('docker', ['compose', 'version'])) {
    throw new Error('需要 Docker Compose v2，请更新 Docker Desktop 后重试')
  }
  if (commandWorks('docker', ['info'])) return

  if (process.platform !== 'darwin' || !process.stdin.isTTY) {
    throw new Error('Docker 未运行。请启动 Docker Desktop，等待其显示 Running 后重试')
  }
  if (!(await askYesNo('Docker Desktop 尚未运行，是否现在启动并等待就绪', true))) {
    throw new Error('Docker 未运行。启动 Docker Desktop 后再次执行 scholarseeker start')
  }
  const opened = spawnSync('open', ['-a', 'Docker'], { stdio: 'ignore' })
  if (opened.status !== 0) {
    throw new Error('无法启动 Docker Desktop。请确认已经安装，然后手动打开它')
  }

  const timeoutMs = Number(process.env.SCHOLARSEEKER_DOCKER_WAIT_MS || 180000)
  const deadline = Date.now() + timeoutMs
  process.stdout.write('正在等待 Docker Desktop')
  while (Date.now() < deadline) {
    if (commandWorks('docker', ['info'])) {
      process.stdout.write('\n✓ Docker Desktop 已就绪\n')
      return
    }
    process.stdout.write('.')
    await delay(2000)
  }
  process.stdout.write('\n')
  throw new Error('等待 Docker Desktop 超时。确认其显示 Running 后再次执行 scholarseeker start')
}

async function doctor(root) {
  const checks = []
  checks.push(['Docker', commandWorks('docker', ['--version'])])
  checks.push(['Docker Compose v2', commandWorks('docker', ['compose', 'version'])])
  checks.push(['Docker daemon', commandWorks('docker', ['info'])])
  checks.push(['config.yaml', await exists(join(root, 'config.yaml'))])
  checks.push(['.env', await exists(join(root, '.env'))])

  if (await exists(join(root, '.env'))) {
    const env = parseEnv(await readFile(join(root, '.env'), 'utf8'))
    const provider = env.get('LLM_ACTIVE_PROVIDER') || 'deepseek'
    const providerConfig = PROVIDERS[provider]
    checks.push([
      `LLM API Key (${providerConfig?.label || provider})`,
      Boolean(providerConfig && env.get(providerConfig.key)),
    ])
  }
  console.log('')
  for (const [label, ok] of checks) console.log(`${ok ? '✓' : '✗'} ${label}`)
  return checks.every(([, ok]) => ok)
}

async function runScript(root, script, args) {
  const path = join(root, 'scripts', script)
  if (!(await exists(path))) throw new Error(`缺少启动脚本：${path}`)
  const child = spawn('bash', [path, ...args], { cwd: root, stdio: 'inherit' })
  await new Promise((resolveExit, reject) => {
    child.once('error', reject)
    child.once('exit', (code, signal) => {
      if (signal) reject(new Error(`进程被信号 ${signal} 终止`))
      else if (code === 0) resolveExit()
      else reject(new Error(`命令执行失败，退出码 ${code}`))
    })
  })
}

async function runStartScript(root, args) {
  if (!startupAnimationEnabled()) return runScript(root, 'start.sh', args)
  const path = join(root, 'scripts', 'start.sh')
  if (!(await exists(path))) throw new Error(`缺少启动脚本：${path}`)

  printStartupCard()
  const startedAt = Date.now()
  let frame = 0
  let status = args.includes('--no-build')
    ? 'Starting ScholarSeeker services'
    : 'Building ScholarSeeker services'
  let stdout = ''
  let stderr = ''
  const maximumCapturedOutput = 2 * 1024 * 1024
  const child = spawn('bash', [path, ...args], {
    cwd: root,
    env: {
      ...process.env,
      COMPOSE_BAKE: 'true',
      SCHOLARSEEKER_COMPOSE_PROGRESS: 'quiet',
    },
    stdio: ['inherit', 'pipe', 'pipe'],
  })

  const capture = (target, chunk) => {
    const next = `${target}${chunk}`
    return next.length > maximumCapturedOutput ? next.slice(-maximumCapturedOutput) : next
  }
  child.stdout.setEncoding('utf8')
  child.stderr.setEncoding('utf8')
  child.stdout.on('data', (chunk) => {
    stdout = capture(stdout, chunk)
    if (stdout.includes('Waiting for ScholarSeeker services')) {
      status = 'Checking ScholarSeeker service health'
    }
  })
  child.stderr.on('data', (chunk) => {
    stderr = capture(stderr, chunk)
  })

  const render = () => {
    const elapsed = Math.floor((Date.now() - startedAt) / 1000)
    process.stdout.write(`\r\x1b[2K• ${shimmer(status, frame)} \x1b[2m(${elapsed}s)\x1b[0m`)
    frame += 1
  }
  process.stdout.write('\x1b[?25l')
  render()
  const timer = setInterval(render, Number(process.env.SCHOLARSEEKER_ANIMATION_INTERVAL_MS || 65))

  return new Promise((resolveExit, reject) => {
    const cleanup = () => {
      clearInterval(timer)
      process.stdout.write('\r\x1b[2K\x1b[?25h')
    }
    const onInterrupt = () => child.kill('SIGINT')
    process.once('SIGINT', onInterrupt)
    child.once('error', (error) => {
      process.removeListener('SIGINT', onInterrupt)
      cleanup()
      reject(error)
    })
    child.once('exit', (code, signal) => {
      process.removeListener('SIGINT', onInterrupt)
      cleanup()
      const elapsed = ((Date.now() - startedAt) / 1000).toFixed(1)
      if (signal) {
        reject(new Error(`进程被信号 ${signal} 终止`))
        return
      }
      if (code !== 0) {
        if (stdout.trim()) process.stdout.write(`${stdout.trimEnd()}\n`)
        if (stderr.trim()) process.stderr.write(`${stderr.trimEnd()}\n`)
        reject(new Error(`命令执行失败，退出码 ${code}`))
        return
      }

      console.log(`✓ \x1b[1;36mScholarSeeker\x1b[0m services ready \x1b[2m(${elapsed}s)\x1b[0m`)
      const summaryIndex = stdout.indexOf('ScholarSeeker is ready.')
      if (summaryIndex >= 0) {
        const summary = stdout.slice(summaryIndex + 'ScholarSeeker is ready.'.length).trim()
        if (summary) console.log(`\n${summary}`)
      }
      resolveExit()
    })
  })
}

async function main() {
  const [command = '--help', ...args] = process.argv.slice(2)
  if (command === '--help' || command === '-h' || command === 'help') return printHelp()
  if (command === 'init' || command === 'setup' || command === 'start') printBanner()
  if (command === 'init') return initProject(args[0])

  const root = await findProjectRoot()
  if (!root) throw new Error('当前目录不在 ScholarSeeker 项目中，请先运行 scholarseeker init')
  if (command === 'setup') return setupProject(root)
  if (command === 'doctor') {
    if (!(await doctor(root))) process.exitCode = 1
    return
  }
  if (command === 'start') {
    if (!(await exists(join(root, '.env')))) await setupProject(root)
    await ensureDockerReady()
    await resolvePortConflicts(root)
    return runStartScript(root, args)
  }
  if (command === 'stop') return runScript(root, 'stop.sh', args)
  if (command === 'status') return runScript(root, 'status.sh', args)
  if (command === 'logs') return runScript(root, 'logs.sh', args)
  throw new Error(`未知命令：${command}`)
}

main().catch((error) => {
  console.error(`\nScholarSeeker: ${error.message}`)
  process.exitCode = 1
})
