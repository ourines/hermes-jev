import assert from 'node:assert/strict'
import fs from 'node:fs/promises'
import path from 'node:path'
import vm from 'node:vm'

const source = await fs.readFile(path.resolve('desktop/plugin.js'), 'utf8')
const context = vm.createContext({})
const sdk = new vm.SyntheticModule(
  ['host', 'ROUTES_AREA', 'SIDEBAR_NAV_AREA'],
  function () {
    this.setExport('host', { request: async () => ({}) })
    this.setExport('ROUTES_AREA', 'routes')
    this.setExport('SIDEBAR_NAV_AREA', 'sidebar.nav')
  },
  { context }
)
const react = new vm.SyntheticModule(
  ['useEffect', 'useState'],
  function () {
    this.setExport('useEffect', () => {})
    this.setExport('useState', value => [value, () => {}])
  },
  { context }
)
const jsxRuntime = new vm.SyntheticModule(
  ['jsx', 'jsxs'],
  function () {
    this.setExport('jsx', (type, props) => ({ type, props }))
    this.setExport('jsxs', (type, props) => ({ type, props }))
  },
  { context }
)
const module = new vm.SourceTextModule(source, { context })
await module.link(specifier => {
  if (specifier === '@hermes/plugin-sdk') return sdk
  if (specifier === 'react') return react
  if (specifier === 'react/jsx-runtime') return jsxRuntime
  throw new Error(`Unexpected import: ${specifier}`)
})
await module.evaluate()

const { catalogRoutes, settingsFromPluginRows, settingsValues } = module.namespace
assert.deepEqual(
  Array.from(catalogRoutes({ providers: [
    { slug: 'provider-a', authenticated: true, models: ['model-a', 'model-b'] },
    { slug: 'provider-b', authenticated: false, models: ['model-c'] }
  ] }), route => `${route.provider}/${route.model}`),
  ['provider-a/model-a', 'provider-a/model-b']
)
const sharedRoutes = catalogRoutes({ providers: [
  { slug: 'provider-a', authenticated: true, models: ['shared/model'] },
  { slug: 'provider-b', authenticated: true, models: ['shared/model'] }
] })
assert.equal(sharedRoutes.length, 2)
assert.equal(new Set(sharedRoutes.map(route => route.id)).size, 2)
for (const route of sharedRoutes) {
  assert.match(route.id, /^[a-zA-Z0-9][a-zA-Z0-9._-]{0,63}$/)
}
assert.deepEqual(
  JSON.parse(JSON.stringify(settingsFromPluginRows({ plugins: [{
    key: 'jev', settings_schema: [
      { key: 'model_route_enabled', value: true },
      { key: 'model_routes', value: [{ provider: 'provider-a', model: 'model-a' }] },
      { key: 'route_min_confidence', value: 0.7 }
    ]
  }] }))),
  {
    enabled: true,
    routes: [{ provider: 'provider-a', model: 'model-a' }],
    minConfidence: 0.7
  }
)
assert.equal(settingsValues(true, [], '').route_min_confidence, 0)
const contributions = []
module.namespace.default.register({ registerMany: rows => contributions.push(...rows) })
assert.ok(contributions.some(item => item.area === 'routes' && item.data.path === '/jev'))
assert.ok(contributions.some(item => item.area === 'sidebar.nav' && item.data.path === '/jev'))
