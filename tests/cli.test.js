import assert from 'node:assert/strict'
import { spawnSync } from 'node:child_process'
import {
  chmodSync,
  copyFileSync,
  existsSync,
  mkdirSync,
  mkdtempSync,
  readFileSync,
  writeFileSync,
} from 'node:fs'
import { tmpdir } from 'node:os'
import { createServer } from 'node:net'
import { join, resolve } from 'node:path'
import test from 'node:test'

const root = resolve(import.meta.dirname, '..')
const cli = join(root, 'bin', 'scholarseeker.js')

test('prints CLI help', () => {
  const result = spawnSync(process.execPath, [cli, '--help'], { encoding: 'utf8' })
  assert.equal(result.status, 0)
  assert.match(result.stdout, /scholarseeker init/)
  assert.match(result.stdout, /scholarseeker setup/)
})

test('shows the competition project banner when initializing', () => {
  const destination = join(mkdtempSync(join(tmpdir(), 'scholarseeker-banner-')), 'project')
  const result = spawnSync(process.execPath, [cli, 'init', destination], {
    encoding: 'utf8',
    stdio: ['ignore', 'pipe', 'pipe'],
  })

  assert.equal(result.status, 0, result.stderr)
  assert.match(result.stdout, /第八届中国研究生人工智能创新大赛企业赛题-科研场景下复杂学术查询的智能论文搜索与推荐演示项目/)
})

test('creates a clean project without copying local secrets or dependencies', () => {
  const destination = join(mkdtempSync(join(tmpdir(), 'scholarseeker-cli-')), 'project')
  const result = spawnSync(process.execPath, [cli, 'init', destination], {
    encoding: 'utf8',
    stdio: ['ignore', 'pipe', 'pipe'],
  })

  assert.equal(result.status, 0, result.stderr)
  assert.equal(existsSync(join(destination, 'docker-compose.yml')), true)
  assert.equal(existsSync(join(destination, '.gitignore')), true)
  assert.equal(existsSync(join(destination, '.env')), false)
  assert.equal(existsSync(join(destination, 'config.yaml')), false)
  assert.equal(existsSync(join(destination, 'scholarseeker-api', 'venv')), false)
  assert.equal(existsSync(join(destination, 'scholarseeker-web', 'node_modules')), false)
})

test('explains how to recover when Docker is installed but not running', () => {
  const temporary = mkdtempSync(join(tmpdir(), 'scholarseeker-docker-'))
  const destination = join(temporary, 'project')
  const initialized = spawnSync(process.execPath, [cli, 'init', destination], {
    encoding: 'utf8',
    stdio: ['ignore', 'pipe', 'pipe'],
  })
  assert.equal(initialized.status, 0, initialized.stderr)
  copyFileSync(join(destination, '.env.example'), join(destination, '.env'))
  copyFileSync(join(destination, 'config_example.yaml'), join(destination, 'config.yaml'))

  const fakeBin = join(temporary, 'bin')
  mkdirSync(fakeBin)
  const fakeDocker = join(fakeBin, 'docker')
  writeFileSync(fakeDocker, '#!/bin/sh\n[ "$1" = "info" ] && exit 1\nexit 0\n')
  chmodSync(fakeDocker, 0o755)
  const result = spawnSync(process.execPath, [cli, 'start'], {
    cwd: destination,
    encoding: 'utf8',
    stdio: ['ignore', 'pipe', 'pipe'],
    env: { ...process.env, PATH: `${fakeBin}:${process.env.PATH}` },
  })

  assert.equal(result.status, 1)
  assert.match(result.stderr, /Docker 未运行。请启动 Docker Desktop/)
})

test('moves an occupied web port and continues startup', async (context) => {
  const blocker = createServer()
  await new Promise((resolveListen) => blocker.listen(0, '0.0.0.0', resolveListen))
  context.after(() => blocker.close())
  const occupiedPort = blocker.address().port

  const temporary = mkdtempSync(join(tmpdir(), 'scholarseeker-port-'))
  const destination = join(temporary, 'project')
  const initialized = spawnSync(process.execPath, [cli, 'init', destination], {
    encoding: 'utf8',
    stdio: ['ignore', 'pipe', 'pipe'],
  })
  assert.equal(initialized.status, 0, initialized.stderr)
  copyFileSync(join(destination, '.env.example'), join(destination, '.env'))
  copyFileSync(join(destination, 'config_example.yaml'), join(destination, 'config.yaml'))
  const envPath = join(destination, '.env')
  const configured = readFileSync(envPath, 'utf8').replace(/^WEB_PORT=.*$/m, `WEB_PORT=${occupiedPort}`)
  writeFileSync(envPath, configured)

  const fakeBin = join(temporary, 'bin')
  mkdirSync(fakeBin)
  const fakeDocker = join(fakeBin, 'docker')
  writeFileSync(
    fakeDocker,
    '#!/bin/sh\n[ "$1" = "compose" ] && [ "$2" = "port" ] && exit 1\nexit 0\n',
  )
  chmodSync(fakeDocker, 0o755)
  const fakeCurl = join(fakeBin, 'curl')
  writeFileSync(fakeCurl, '#!/bin/sh\nexit 0\n')
  chmodSync(fakeCurl, 0o755)

  const result = spawnSync(process.execPath, [cli, 'start'], {
    cwd: destination,
    encoding: 'utf8',
    stdio: ['ignore', 'pipe', 'pipe'],
    env: { ...process.env, PATH: `${fakeBin}:${process.env.PATH}` },
  })
  const saved = readFileSync(envPath, 'utf8')

  assert.equal(result.status, 0, result.stderr)
  assert.match(result.stdout, /ScholarSeeker 正在启动/)
  assert.match(result.stdout, new RegExp(`Web 端口 ${occupiedPort} 已被占用，自动改用`))
  assert.doesNotMatch(saved, new RegExp(`^WEB_PORT=${occupiedPort}$`, 'm'))
})
