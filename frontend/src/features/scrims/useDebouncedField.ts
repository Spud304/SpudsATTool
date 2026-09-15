import { useEffect, useRef, useState } from 'react'

/**
 * Free text on a shared document: keep the local draft while typing, save 400 ms after the last
 * keystroke and on blur, and only take the server's value while the field is not focused.
 */
export function useDebouncedField(server: string, save: (value: string) => void, delay = 400) {
  const [value, setValue] = useState(server)
  const latest = useRef(server)
  const focused = useRef(false)
  const timer = useRef<number | undefined>(undefined)

  useEffect(() => {
    if (!focused.current) {
      setValue(server)
      latest.current = server
    }
  }, [server])

  const flush = () => {
    window.clearTimeout(timer.current)
    if (latest.current !== server) save(latest.current)
  }
  return {
    value,
    onChange: (next: string) => {
      setValue(next)
      latest.current = next
      window.clearTimeout(timer.current)
      timer.current = window.setTimeout(() => save(latest.current), delay)
    },
    onFocus: () => {
      focused.current = true
    },
    onBlur: () => {
      focused.current = false
      flush()
    },
  }
}
