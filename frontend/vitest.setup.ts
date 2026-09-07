class LocalStorageMock {
  private values = new Map<string, string>()

  getItem(key: string) {
    return this.values.get(key) ?? null
  }

  setItem(key: string, value: string) {
    this.values.set(key, value)
  }

  removeItem(key: string) {
    this.values.delete(key)
  }

  clear() {
    this.values.clear()
  }
}

const storage = new LocalStorageMock()

if (!globalThis.localStorage) {
  Object.defineProperty(globalThis, 'localStorage', {
    value: storage,
    configurable: true,
    writable: true
  })
}

if (!globalThis.window) {
  Object.defineProperty(globalThis, 'window', {
    value: {
      localStorage: storage,
      location: { pathname: '/', href: '/' },
      navigator: { userAgent: 'vitest' }
    },
    configurable: true,
    writable: true
  })
}

if (!globalThis.navigator) {
  Object.defineProperty(globalThis, 'navigator', {
    value: { userAgent: 'vitest' },
    configurable: true,
    writable: true
  })
}

if (!globalThis.document) {
  Object.defineProperty(globalThis, 'document', {
    value: {
      documentElement: {
        classList: {
          toggle() {}
        },
        lang: ''
      },
      createElement: () => ({
        content: { firstChild: null },
        style: {},
        setAttribute() {},
        getAttribute: () => null,
        cloneNode: () => null,
        querySelector: () => null
      }),
      createElementNS: () => ({
        style: {},
        setAttribute() {},
        getAttribute: () => null,
        cloneNode: () => null,
        querySelector: () => null
      }),
      addEventListener() {},
      removeEventListener() {},
      dispatchEvent: () => true,
      createTextNode: () => ({}),
      createComment: () => ({}),
      querySelector: () => null,
      title: ''
    },
    configurable: true,
    writable: true
  })
}
