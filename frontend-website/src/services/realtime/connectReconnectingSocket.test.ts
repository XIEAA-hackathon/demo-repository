import { strict as assert } from 'node:assert'
import { connectReconnectingSocket } from './connectReconnectingSocket.ts'

type OpenHandler = (() => void) | null
type CloseHandler = ((event: Pick<CloseEvent, 'code' | 'reason' | 'wasClean'>) => void) | null

class FakeWebSocket {
  static instances: FakeWebSocket[] = []
  static OPEN = 1

  readonly url: string
  onopen: OpenHandler = null
  onmessage: ((event: Pick<MessageEvent, 'data'>) => void) | null = null
  onerror: (() => void) | null = null
  onclose: CloseHandler = null
  closed = false
  readyState = 0
  sent: string[] = []

  constructor(url: string) {
    this.url = url
    FakeWebSocket.instances.push(this)
  }

  open() {
    this.readyState = FakeWebSocket.OPEN
    this.onopen?.()
  }

  send(message: string) { this.sent.push(message) }

  forceClose(code = 1006, reason = 'test disconnect') {
    this.closed = true
    this.readyState = 3
    this.onclose?.({ code, reason, wasClean: false })
  }

  close() {
    if (this.closed) return
    this.closed = true
    this.readyState = 3
    this.onclose?.({ code: 1000, reason: '', wasClean: true })
  }
}

Object.assign(globalThis, {
  window: { setTimeout, clearTimeout, setInterval, clearInterval },
  WebSocket: FakeWebSocket,
})

const statuses: string[] = []
const diagnostics: unknown[] = []
const originalInfo = console.info
console.info = (...args: unknown[]) => { diagnostics.push(args) }

try {
  const disconnect = connectReconnectingSocket({
    url: 'ws://test.invalid/ws/auction',
    getToken: () => 'secret-test-token',
    onStatus: (status) => statuses.push(status),
    heartbeatIntervalMs: 20,
  })

  assert.equal(FakeWebSocket.instances.length, 1)
  assert.deepEqual(statuses, ['connecting'])
  FakeWebSocket.instances[0].open()
  assert.equal(statuses.at(-1), 'connected')
  await new Promise((resolve) => setTimeout(resolve, 25))
  assert.deepEqual(FakeWebSocket.instances[0].sent, ['heartbeat'])

  FakeWebSocket.instances[0].forceClose()
  assert.equal(statuses.at(-1), 'reconnecting')
  await new Promise((resolve) => setTimeout(resolve, 1_250))
  assert.equal(FakeWebSocket.instances.length, 2)

  FakeWebSocket.instances[1].open()
  assert.equal(statuses.at(-1), 'reconnected')
  await new Promise((resolve) => setTimeout(resolve, 2_050))
  assert.equal(statuses.at(-1), 'connected')

  disconnect()
  assert.equal(statuses.at(-1), 'disconnected')
  await new Promise((resolve) => setTimeout(resolve, 1_050))
  assert.equal(FakeWebSocket.instances.length, 2)

  let unauthorized = false
  const unauthorizedSocket = connectReconnectingSocket({
    url: 'ws://test.invalid/ws/auction',
    getToken: () => 'revoked-test-token',
    onUnauthorized: () => { unauthorized = true },
  })
  const rejected = FakeWebSocket.instances.at(-1)!
  rejected.open()
  rejected.forceClose(4401, 'Session revoked')
  assert.equal(unauthorized, true)
  await new Promise((resolve) => setTimeout(resolve, 1_050))
  assert.equal(FakeWebSocket.instances.at(-1), rejected)
  unauthorizedSocket()

  const diagnosticText = JSON.stringify(diagnostics)
  assert.doesNotMatch(diagnosticText, /secret-test-token/)
  assert.match(diagnosticText, /test disconnect/)
} finally {
  console.info = originalInfo
}

console.log('realtime socket lifecycle: all assertions passed')
