import assert from 'node:assert/strict'
import { spawnSync } from 'node:child_process'
import { existsSync, mkdtempSync } from 'node:fs'
import { tmpdir } from 'node:os'
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
