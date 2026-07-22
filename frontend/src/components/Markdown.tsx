import { useMemo } from 'react'

/**
 * Renders the Markdown subset our prompts produce (h2, bullets, bold, italic,
 * inline code). Deliberately not a Markdown library: the input is a known shape
 * from our own prompts, and every third-party renderer is a potential XSS hole.
 * Text is written via JSX children, so React escapes it — there is no
 * dangerouslySetInnerHTML anywhere in this app.
 */
export default function Markdown({ source }: { source: string }) {
  const blocks = useMemo(() => {
    const out: React.ReactNode[] = []
    let list: string[] = []
    let key = 0

    const flushList = () => {
      if (list.length === 0) return
      out.push(
        <ul key={`ul-${key++}`}>
          {list.map((item, i) => (
            <li key={i}>
              <Inline text={item} />
            </li>
          ))}
        </ul>,
      )
      list = []
    }

    for (const raw of source.split('\n')) {
      const line = raw.trim()
      if (!line) {
        flushList()
        continue
      }
      if (line.startsWith('## ')) {
        flushList()
        out.push(<h2 key={`h-${key++}`}>{line.slice(3)}</h2>)
      } else if (line.startsWith('# ')) {
        flushList()
        out.push(<h2 key={`h-${key++}`}>{line.slice(2)}</h2>)
      } else if (/^[-*]\s+/.test(line)) {
        list.push(line.replace(/^[-*]\s+/, ''))
      } else {
        flushList()
        out.push(
          <p key={`p-${key++}`}>
            <Inline text={line} />
          </p>,
        )
      }
    }
    flushList()
    return out
  }, [source])

  return <div className="md">{blocks}</div>
}

/** Handles **bold**, *italic* and `code` without touching innerHTML. */
export function Inline({ text }: { text: string }) {
  const parts = useMemo(() => {
    const nodes: React.ReactNode[] = []
    const re = /(\*\*[^*]+\*\*|`[^`]+`|\*[^*]+\*)/g
    let last = 0
    let m: RegExpExecArray | null
    let i = 0

    while ((m = re.exec(text)) !== null) {
      if (m.index > last) nodes.push(text.slice(last, m.index))
      const token = m[0]
      if (token.startsWith('**')) nodes.push(<strong key={i++}>{token.slice(2, -2)}</strong>)
      else if (token.startsWith('`')) nodes.push(<code key={i++}>{token.slice(1, -1)}</code>)
      else nodes.push(<em key={i++}>{token.slice(1, -1)}</em>)
      last = m.index + token.length
    }
    if (last < text.length) nodes.push(text.slice(last))
    return nodes
  }, [text])

  return <>{parts}</>
}
