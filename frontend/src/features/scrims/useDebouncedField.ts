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

  // Only a keystroke makes a save due: without it, a blur would write back the stale copy held
  // since focus over whatever someone else saved meanwhile.
  const typed = useRef(false)
  const send = () => {
    window.clearTimeout(timer.current)
    if (!typed.current) return
    typed.current = false
    save(latest.current)
  }
  return {
    value,
    onChange: (next: string) => {
      setValue(next)
      latest.current = next
      typed.current = true
      window.clearTimeout(timer.current)
      timer.current = window.setTimeout(send, delay)
    },
    onFocus: () => {
      focused.current = true
    },
    onBlur: () => {
      focused.current = false
      if (typed.current) send()
      else {
        // Nothing typed: show what the server holds now, which may have changed while focused.
        setValue(server)
        latest.current = server
      }
    },
  }
}
