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
const cli = join(root, 'bin', 'esasr.js')

test('prints CLI help', () => {
  const result = spawnSync(process.execPath, [cli, '--help'], { encoding: 'utf8' })
  assert.equal(result.status, 0)
  assert.match(result.stdout, /esasr init/)
  assert.match(result.stdout, /esasr setup/)
  assert.match(result.stdout, /esasr restart/)
  assert.match(result.stdout, /esasr academic add/)
  assert.match(result.stdout, /esasr key add/)
  assert.match(result.stdout, /esasr provider use/)
  assert.match(result.stdout, /esasr cache clear/)
})

test('lists and clears only shared query planning cache keys', () => {
  const temporary = mkdtempSync(join(tmpdir(), 'esasr-cache-management-'))
  const destination = join(temporary, 'project')
  const initialized = spawnSync(process.execPath, [cli, 'init', destination], {
    encoding: 'utf8',
    stdio: ['ignore', 'pipe', 'pipe'],
  })
  assert.equal(initialized.status, 0, initialized.stderr)

  const fakeBin = join(temporary, 'bin')
  mkdirSync(fakeBin)
  const dockerLog = join(temporary, 'docker.log')
  const fakeDocker = join(fakeBin, 'docker')
  writeFileSync(fakeDocker, `#!/bin/sh
echo "$*" >> "${dockerLog}"
case "$*" in
  *"redis-cli --scan --pattern query_plan:"*)
    echo "query_plan:v3:deepseek:model:first"
    echo "query_plan:v3:deepseek:model:second"
    ;;
  *"redis-cli del "*) echo "2" ;;
esac
exit 0
`)
  chmodSync(fakeDocker, 0o755)
  const env = { ...process.env, PATH: `${fakeBin}:${process.env.PATH}` }

  const status = spawnSync(process.execPath, [cli, 'cache', 'status'], {
    cwd: destination, encoding: 'utf8', env,
  })
  assert.equal(status.status, 0, status.stderr)
  assert.match(status.stdout, /共享规划缓存：2 条/)

  const cleared = spawnSync(process.execPath, [cli, 'cache', 'clear', '--yes'], {
    cwd: destination, encoding: 'utf8', env,
  })
  assert.equal(cleared.status, 0, cleared.stderr)
  assert.match(cleared.stdout, /已清除 2 条共享规划缓存/)
  const commands = readFileSync(dockerLog, 'utf8')
  assert.match(commands, /redis-cli del query_plan:/)
  assert.doesNotMatch(commands, /FLUSHDB|FLUSHALL/i)
})

test('shows the competition project banner when initializing', () => {
  const destination = join(mkdtempSync(join(tmpdir(), 'scholarseeker-banner-')), 'project')
  const result = spawnSync(process.execPath, [cli, 'init', destination], {
    encoding: 'utf8',
    stdio: ['ignore', 'pipe', 'pipe'],
  })

  assert.equal(result.status, 0, result.stderr)
  const bannerLines = result.stdout.split('\n').filter((line) => /^[╔║╚]/.test(line))
  assert.equal(bannerLines.length, 4)
  assert.ok(bannerLines.every((line) => terminalWidth(line) <= 80))
  const renderedTitle = bannerLines
    .filter((line) => line.startsWith('║'))
    .map((line) => line.slice(1, -1).trim())
  assert.deepEqual(renderedTitle, [
    '第八届中国研究生人工智能创新大赛企业赛题',
    '科研场景下复杂学术查询的智能论文搜索与推荐演示项目',
  ])
  for (const line of bannerLines.filter((value) => value.startsWith('║'))) {
    const content = line.slice(1, -1)
    const leading = content.match(/^ */)[0].length
    const trailing = content.match(/ *$/)[0].length
    assert.ok(Math.abs(leading - trailing) <= 1)
  }
})

function terminalWidth(value) {
  return Array.from(value).reduce((width, character) => {
    if (/\p{Mark}/u.test(character)) return width
    return width + (/[\u2e80-\ua4cf\uac00-\ud7a3\uf900-\ufaff\uff00-\uff60]/u.test(character) ? 2 : 1)
  }, 0)
}

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
  assert.equal(existsSync(join(destination, 'esasr-api', 'venv')), false)
  assert.equal(existsSync(join(destination, 'esasr-web', 'node_modules')), false)
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
  assert.match(result.stdout, /Waiting for ESASR services/)
  assert.match(result.stdout, new RegExp(`Web 端口 ${occupiedPort} 已被占用，自动改用`))
  assert.doesNotMatch(saved, new RegExp(`^WEB_PORT=${occupiedPort}$`, 'm'))
})

test('renders the ESASR branded startup card and progress status', async () => {
  const temporary = mkdtempSync(join(tmpdir(), 'scholarseeker-animation-'))
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
  writeFileSync(fakeDocker, '#!/bin/sh\nexit 0\n')
  chmodSync(fakeDocker, 0o755)
  const fakeCurl = join(fakeBin, 'curl')
  writeFileSync(fakeCurl, '#!/bin/sh\nexit 0\n')
  chmodSync(fakeCurl, 0o755)

  const result = spawnSync(process.execPath, [cli, 'start'], {
    cwd: destination,
    encoding: 'utf8',
    stdio: ['ignore', 'pipe', 'pipe'],
    env: {
      ...process.env,
      PATH: `${fakeBin}:${process.env.PATH}`,
      SCHOLARSEEKER_FORCE_ANIMATION: '1',
      SCHOLARSEEKER_ANIMATION_INTERVAL_MS: '0',
      SCHOLARSEEKER_BANNER_INTERVAL_MS: '0',
    },
  })

  assert.equal(result.status, 0, result.stderr)
  const plainOutput = result.stdout.replace(/\x1b\[[0-9;?]*[A-Za-z]/g, '')
  assert.match(result.stdout, /^\x1b\[2J\x1b\[H/)
  assert.match(result.stdout, /\x1b\[1;91m/)
  assert.match(result.stdout, /\x1b\[1;94m/)
  assert.match(plainOutput, /第八届中国研究生人工智能创新大赛企业赛题/)
  assert.match(plainOutput, /科研场景下复杂学术查询的智能论文搜索与推荐演示项目/)
  assert.doesNotMatch(plainOutput, /企业赛题-科研场景/)
  assert.match(plainOutput, />_ ESASR/)
  assert.match(plainOutput, /Building ESASR services/)
  assert.match(plainOutput, /ESASR services ready/)
  assert.doesNotMatch(plainOutput, /Compose can now delegate builds/)
})

test('adds, updates, lists, selects, and removes provider API keys safely', () => {
  const temporary = mkdtempSync(join(tmpdir(), 'scholarseeker-key-management-'))
  const destination = join(temporary, 'project')
  const initialized = spawnSync(process.execPath, [cli, 'init', destination], {
    encoding: 'utf8',
    stdio: ['ignore', 'pipe', 'pipe'],
  })
  assert.equal(initialized.status, 0, initialized.stderr)

  const added = spawnSync(process.execPath, [cli, 'key', 'add', 'deepseek'], {
    cwd: destination,
    encoding: 'utf8',
    env: { ...process.env, ESASR_MODEL_API_KEY: 'sk-added-secret' },
  })
  assert.equal(added.status, 0, added.stderr)
  assert.doesNotMatch(added.stdout, /sk-added-secret/)
  assert.match(readFileSync(join(destination, '.env'), 'utf8'), /^DEEPSEEK_API_KEY=sk-added-secret$/m)

  const listed = spawnSync(process.execPath, [cli, 'key', 'list'], {
    cwd: destination,
    encoding: 'utf8',
  })
  assert.equal(listed.status, 0, listed.stderr)
  assert.match(listed.stdout, /DeepSeek\s+✓ 已配置 Key/)
  assert.doesNotMatch(listed.stdout, /sk-added-secret/)

  const selected = spawnSync(process.execPath, [cli, 'provider', 'use', 'deepseek'], {
    cwd: destination,
    encoding: 'utf8',
  })
  assert.equal(selected.status, 0, selected.stderr)
  assert.match(selected.stdout, /默认大模型平台已切换为 DeepSeek/)

  const updated = spawnSync(process.execPath, [cli, 'key', 'update', 'deepseek'], {
    cwd: destination,
    encoding: 'utf8',
    env: { ...process.env, ESASR_MODEL_API_KEY: 'sk-updated-secret' },
  })
  assert.equal(updated.status, 0, updated.stderr)
  assert.doesNotMatch(updated.stdout, /sk-updated-secret/)
  assert.match(readFileSync(join(destination, '.env'), 'utf8'), /^DEEPSEEK_API_KEY=sk-updated-secret$/m)

  const config = spawnSync(process.execPath, [cli, 'config'], {
    cwd: destination,
    encoding: 'utf8',
  })
  assert.equal(config.status, 0, config.stderr)
  assert.match(config.stdout, /默认平台：deepseek · DeepSeek/)
  assert.match(config.stdout, /安全提示：API Key 内容已隐藏/)
  assert.doesNotMatch(config.stdout, /sk-updated-secret/)

  const removed = spawnSync(process.execPath, [cli, 'key', 'remove', 'deepseek', '--yes'], {
    cwd: destination,
    encoding: 'utf8',
  })
  assert.equal(removed.status, 0, removed.stderr)
  assert.match(removed.stdout, /API Key 已从本机 .env 删除/)
  assert.match(readFileSync(join(destination, '.env'), 'utf8'), /^DEEPSEEK_API_KEY=$/m)
})

test('configures and removes academic search API keys safely', () => {
  const temporary = mkdtempSync(join(tmpdir(), 'esasr-academic-key-management-'))
  const destination = join(temporary, 'project')
  const initialized = spawnSync(process.execPath, [cli, 'init', destination], {
    encoding: 'utf8',
    stdio: ['ignore', 'pipe', 'pipe'],
  })
  assert.equal(initialized.status, 0, initialized.stderr)

  const semanticAdded = spawnSync(process.execPath, [cli, 'academic', 'add', 's2'], {
    cwd: destination,
    encoding: 'utf8',
    env: { ...process.env, ESASR_ACADEMIC_API_KEY: 's2-secret' },
  })
  assert.equal(semanticAdded.status, 0, semanticAdded.stderr)
  assert.doesNotMatch(semanticAdded.stdout, /s2-secret/)

  const openAlexAdded = spawnSync(process.execPath, [cli, 'academic', 'set', 'openalex'], {
    cwd: destination,
    encoding: 'utf8',
    env: {
      ...process.env,
      ESASR_ACADEMIC_API_KEY: 'openalex-secret',
      ESASR_OPENALEX_EMAIL: 'research@example.com',
    },
  })
  assert.equal(openAlexAdded.status, 0, openAlexAdded.stderr)
  assert.doesNotMatch(openAlexAdded.stdout, /openalex-secret/)

  const envContent = readFileSync(join(destination, '.env'), 'utf8')
  assert.ok(envContent.includes('SEMANTIC_SCHOLAR_API_KEY=s2-secret'))
  assert.ok(envContent.includes('OPENALEX_API_KEY=openalex-secret'))
  assert.ok(envContent.includes('OPENALEX_EMAIL=research@example.com'))

  const listed = spawnSync(process.execPath, [cli, 'academic', 'list'], {
    cwd: destination,
    encoding: 'utf8',
  })
  assert.equal(listed.status, 0, listed.stderr)
  assert.match(listed.stdout, /Semantic Scholar\s+✓ 已配置 Key/)
  assert.match(listed.stdout, /OpenAlex\s+✓ 已配置 Key · 联系邮箱已配置/)
  assert.doesNotMatch(listed.stdout, /s2-secret|openalex-secret/)

  const config = spawnSync(process.execPath, [cli, 'config'], {
    cwd: destination,
    encoding: 'utf8',
  })
  assert.equal(config.status, 0, config.stderr)
  assert.match(config.stdout, /已配置学术搜索 Key：semantic-scholar、openalex/)
  assert.doesNotMatch(config.stdout, /s2-secret|openalex-secret/)

  const removed = spawnSync(process.execPath, [cli, 'academic', 'remove', 'openalex', '--yes'], {
    cwd: destination,
    encoding: 'utf8',
  })
  assert.equal(removed.status, 0, removed.stderr)
  const removedEnv = readFileSync(join(destination, '.env'), 'utf8')
  assert.ok(removedEnv.includes('OPENALEX_API_KEY='))
  assert.ok(removedEnv.includes('OPENALEX_EMAIL='))
})

test('restarts services without rebuilding when requested', () => {
  const temporary = mkdtempSync(join(tmpdir(), 'scholarseeker-restart-'))
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
  writeFileSync(fakeDocker, '#!/bin/sh\nexit 0\n')
  chmodSync(fakeDocker, 0o755)
  const fakeCurl = join(fakeBin, 'curl')
  writeFileSync(fakeCurl, '#!/bin/sh\nexit 0\n')
  chmodSync(fakeCurl, 0o755)

  const restarted = spawnSync(process.execPath, [cli, 'restart', '--no-build'], {
    cwd: destination,
    encoding: 'utf8',
    stdio: ['ignore', 'pipe', 'pipe'],
    env: { ...process.env, PATH: `${fakeBin}:${process.env.PATH}` },
  })
  assert.equal(restarted.status, 0, restarted.stderr)
  assert.match(restarted.stdout, /ESASR is ready/)
})
