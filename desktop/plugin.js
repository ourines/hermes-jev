import { host, ROUTES_AREA, SIDEBAR_NAV_AREA } from '@hermes/plugin-sdk'
import { useEffect, useState } from 'react'
import { jsx, jsxs } from 'react/jsx-runtime'

const pairKey = route => `${route.provider}\u0000${route.model}`

export function catalogRoutes(payload) {
  const providers = Array.isArray(payload?.providers) ? payload.providers : []
  const routes = []
  for (const provider of providers) {
    if (provider?.authenticated !== true || !provider.slug) continue
    for (const item of provider.models || []) {
      const model = typeof item === 'string' ? item : item?.id
      if (typeof model !== 'string' || !model.trim()) continue
      routes.push({
        id: `${provider.slug}:${model}`,
        provider: provider.slug,
        model,
        description: `${provider.name || provider.slug} · ${model}`
      })
    }
  }
  return routes
}

export function settingsFromPluginRows(payload) {
  const plugin = (payload?.plugins || []).find(row => row?.key === 'jev' || row?.name === 'jev')
  const fields = new Map((plugin?.settings_schema || []).map(field => [field.key, field.value ?? field.default]))
  const routes = fields.get('model_routes')
  const threshold = fields.get('route_min_confidence')
  return {
    enabled: fields.get('model_route_enabled') === true,
    routes: Array.isArray(routes) ? routes : [],
    minConfidence: typeof threshold === 'number' ? threshold : null
  }
}

export function settingsValues(enabled, routes, minConfidence) {
  return {
    model_route_enabled: enabled,
    model_routes: routes,
    route_min_confidence: minConfidence === '' ? 0 : Number(minConfidence)
  }
}

const buttonStyle = {
  border: '1px solid var(--ui-border)',
  borderRadius: '8px',
  padding: '8px 14px'
}

function SettingsPage() {
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState('')
  const [saved, setSaved] = useState(false)
  const [models, setModels] = useState([])
  const [enabled, setEnabled] = useState(false)
  const [routes, setRoutes] = useState([])
  const [minConfidence, setMinConfidence] = useState('')

  useEffect(() => {
    let active = true
    Promise.all([
      host.request('model.options', { explicit_only: true, include_unconfigured: false }),
      host.request('plugins.manage', { action: 'list' })
    ]).then(([inventory, plugins]) => {
      if (!active) return
      const settings = settingsFromPluginRows(plugins)
      setModels(catalogRoutes(inventory))
      setEnabled(settings.enabled)
      setRoutes(settings.routes)
      setMinConfidence(settings.minConfidence === null ? '' : String(settings.minConfidence))
    }).catch(cause => {
      if (active) setError(cause instanceof Error ? cause.message : String(cause))
    }).finally(() => {
      if (active) setLoading(false)
    })
    return () => { active = false }
  }, [])

  const selected = new Set(routes.map(pairKey))
  const toggleRoute = route => {
    const key = pairKey(route)
    setRoutes(current => current.some(item => pairKey(item) === key)
      ? current.filter(item => pairKey(item) !== key)
      : [...current, route])
    setSaved(false)
  }
  const save = async () => {
    setSaving(true)
    setError('')
    setSaved(false)
    try {
      const values = settingsValues(enabled, routes, minConfidence)
      const result = await host.request('plugins.manage', {
        action: 'settings', key: 'jev', values
      })
      if (result?.ok === false) throw new Error('Could not save Jev settings')
      setSaved(true)
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : String(cause))
    } finally {
      setSaving(false)
    }
  }

  const invalidSelection = enabled && (routes.length === 1 || routes.length > 32)
  const invalidThreshold = minConfidence !== '' &&
    (!Number.isFinite(Number(minConfidence)) || Number(minConfidence) < 0 || Number(minConfidence) > 1)

  return jsxs('main', {
    className: 'mx-auto flex max-w-3xl flex-col gap-5 overflow-y-auto p-6 text-sm',
    children: [
      jsx('h1', { className: 'text-xl font-semibold', children: 'Jev model routing' }),
      jsx('p', {
        className: 'text-(--ui-text-secondary)',
        children: 'Choose which configured Hermes models Jev may use for each new turn.'
      }),
      loading ? jsx('p', { children: 'Loading models…' }) : jsxs('div', {
        className: 'flex flex-col gap-5',
        children: [
          jsx('label', {
            className: 'flex items-center gap-2',
            children: jsxs('span', { className: 'flex items-center gap-2', children: [
              jsx('input', { type: 'checkbox', checked: enabled, onChange: event => {
                setEnabled(event.target.checked); setSaved(false)
              } }),
              'Automatically route each user turn'
            ] })
          }),
          jsx('p', {
            className: 'text-(--ui-text-secondary)',
            children: 'Leave all models unchecked to use the configured model inventory automatically. Select two or more to limit routing to your choices.'
          }),
          models.length === 0 ? jsx('p', { children: 'No authenticated model catalog is available.' }) :
            jsx('div', {
              className: 'grid max-h-96 gap-2 overflow-y-auto',
              children: models.map(route => jsx('label', {
                className: 'flex items-center gap-2 rounded-md p-2',
                style: { border: '1px solid var(--ui-border)' },
                children: jsxs('span', { className: 'flex items-center gap-2', children: [
                  jsx('input', {
                    type: 'checkbox', checked: selected.has(pairKey(route)),
                    onChange: () => toggleRoute(route)
                  }),
                  jsx('span', { children: route.description })
                ] })
              }, pairKey(route)))
            }),
          jsxs('label', { className: 'flex flex-col gap-1', children: [
            jsx('span', { children: 'Minimum routing confidence (optional)' }),
            jsx('input', {
              type: 'number', min: '0', max: '1', step: '0.05', value: minConfidence,
              onChange: event => { setMinConfidence(event.target.value); setSaved(false) },
              className: 'w-32 rounded-md p-2',
              style: { border: '1px solid var(--ui-border)', background: 'var(--ui-bg)' }
            })
          ] }),
          invalidSelection ? jsx('p', { role: 'alert', children: 'Select 2–32 models, or clear the selection for automatic discovery.' }) : null,
          invalidThreshold ? jsx('p', { role: 'alert', children: 'Confidence must be between 0 and 1.' }) : null,
          jsx('button', {
            type: 'button', onClick: save,
            disabled: saving || invalidSelection || invalidThreshold,
            style: buttonStyle,
            className: 'w-fit disabled:opacity-50',
            children: saving ? 'Saving…' : 'Save settings'
          }),
          saved ? jsx('p', { role: 'status', children: 'Settings saved.' }) : null
        ]
      }),
      error ? jsx('p', { role: 'alert', children: error }) : null
    ]
  })
}

export default {
  id: 'jev',
  name: 'Jev',
  register(ctx) {
    ctx.registerMany([
      { id: 'settings', area: ROUTES_AREA, data: { path: '/jev' }, render: () => jsx(SettingsPage, {}) },
      { id: 'nav', area: SIDEBAR_NAV_AREA, data: { path: '/jev', label: 'Jev', codicon: 'symbol-parameter' } }
    ])
  }
}
