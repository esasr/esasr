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
import { dirname, extname, join, relative, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'
import { createInterface } from 'node:readline/promises'

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
  console.log('\n请选择查询规划使用的大模型平台：')
  const names = Object.keys(PROVIDERS)
  names.forEach((name, index) => console.log(`  ${index + 1}. ${PROVIDERS[name].label}`))
  const choice = await ask('输入序号', '1')
  const index = Number(choice) - 1
  if (!Number.isInteger(index) || index < 0 || index >= names.length) {
    throw new Error('无效的平台序号')
  }
  return names[index]
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

async function main() {
  const [command = '--help', ...args] = process.argv.slice(2)
  if (command === '--help' || command === '-h' || command === 'help') return printHelp()
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
    return runScript(root, 'start.sh', args)
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
