'use client'

import { useState } from 'react'
import React from 'react'
import { useABTracking, trackCTAClick, trackFormSubmit, trackModalOpen } from '@/hooks/useABTracking'


// ── AI Terminal Mock Component ──────────────────────────────────────────
function AITerminal({ aiName, status, rank, quote }: {
  aiName: string
  status: 'found' | 'not-found'
  rank?: string
  quote?: string
}) {
  const isFound = status === 'found'
  return (
    <div className="terminal card-hover" style={{ border: `1px solid ${isFound ? 'rgba(255,45,107,0.3)' : 'rgba(136,153,187,0.2)'}` }}>
      <div className="terminal-bar">
        <span className="dot dot-r" />
        <span className="dot dot-y" />
        <span className="dot dot-g" />
        <span style={{ marginLeft: 8, fontSize: 16, color: '#AABBCC', fontFamily: 'Inter, monospace' }}>{aiName}</span>
      </div>
      <div style={{ padding: '16px 20px' }}>
        <p style={{ fontSize: 18, color: '#AABBCC', fontFamily: 'monospace', marginBottom: 8 }}>
          &gt; 「おすすめの〇〇会社は？」
        </p>
        {isFound ? (
          <>
            <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 8 }}>
              <span style={{ 
                background: 'linear-gradient(135deg, #06C755, #04A044)',
                color: 'white', fontSize: 15, padding: '2px 8px', borderRadius: 4, fontWeight: 700
              }}>{rank}</span>
              <span style={{ color: '#FFFFFF', fontSize: 18, fontWeight: 600 }}>競合A社</span>
            </div>
            {quote && (
              <p style={{ fontSize: 18, color: '#CCDDEE', fontStyle: 'italic', lineHeight: 1.6 }}>
                "{quote}"
              </p>
            )}
          </>
        ) : (
          <div style={{ 
            background: 'rgba(136,153,187,0.12)', 
            border: '1px solid rgba(136,153,187,0.25)',
            borderRadius: 8, padding: '12px 16px',
            display: 'flex', alignItems: 'center', gap: 10
          }}>
            <span style={{ fontSize: 24 }}>⚠️</span>
            <div>
              <p style={{ fontSize: 17, color: '#AABBCC' }}>あなたの会社は</p>
              <p style={{ fontSize: 19, color: '#FF8888', fontWeight: 700 }}>表示されていません</p>
            </div>
          </div>
        )}
      </div>
    </div>
  )
}

// ── Diagnosis Result Card ────────────────────────────────────────────────
function DiagnosisCard({ ai, icon, result, detail, color }: {
  ai: string, icon: React.ReactNode, result: string, detail: string, color: string
}) {
  return (
    <div className="card-hover" style={{
      background: 'var(--surface)',
      border: '1px solid rgba(0,0,0,0.07)',
      borderRadius: 12, padding: '20px 24px',
    }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 12 }}>
        <div style={{ flexShrink: 0 }}>{icon}</div>
        <span style={{ fontSize: 19, fontWeight: 700, color: '#1A1A2E' }}>{ai}</span>
      </div>
      <p style={{ fontSize: 19, color: 'var(--muted)', marginBottom: 8 }}>{detail}</p>
      <p style={{ fontSize: 22, fontWeight: 800, color }}>{result}</p>
    </div>
  )
}

// ── Contact Form Modal ───────────────────────────────────────────────────
const GOOGLE_FORM_ACTION = 'https://docs.google.com/forms/d/e/1FAIpQLScnvbLNU7loDCP75dML3zWAMf7mTGBcD58uQJjWMYgV5yw83Q/formResponse'

// ── Chat Form Modal ──────────────────────────────────────────────────────
type Step = 'email' | 'company' | 'name' | 'submitting' | 'done' | 'error'

function FormModal({ onClose, variant }: { onClose: () => void; variant: 'A' | 'B' }) {
  const [step, setStep] = React.useState<Step>('email')
  const [email, setEmail] = React.useState('')
  const [company, setCompany] = React.useState('')
  const [name, setName] = React.useState('')
  const [inputVal, setInputVal] = React.useState('')
  const [error, setError] = React.useState('')
  const inputRef = React.useRef<HTMLInputElement>(null)

  React.useEffect(() => {
    setTimeout(() => inputRef.current?.focus(), 100)
  }, [step])

  const steps: Record<Exclude<Step, 'submitting' | 'done' | 'error'>, {
    bot: string, placeholder: string, type: string, validate: (v: string) => string
  }> = {
    email: {
      bot: 'メールアドレスを教えてください。診断レポートをお送りします。',
      placeholder: 'your@email.com',
      type: 'email',
      validate: (v) => /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(v) ? '' : '正しいメールアドレスを入力してください',
    },
    company: {
      bot: 'ありがとうございます。\n貴社名・屋号を教えてください。',
      placeholder: '株式会社○○',
      type: 'text',
      validate: (v) => v.trim().length > 0 ? '' : '会社名を入力してください',
    },
    name: {
      bot: '最後に、ご担当者様のお名前を教えてください。',
      placeholder: '山田 太郎',
      type: 'text',
      validate: (v) => v.trim().length > 0 ? '' : 'お名前を入力してください',
    },
  }

  const handleNext = async () => {
    if (step === 'submitting' || step === 'done' || step === 'error') return
    const cur = steps[step]
    const err = cur.validate(inputVal)
    if (err) { setError(err); return }
    setError('')

    if (step === 'email') { setEmail(inputVal); setInputVal(''); setStep('company') }
    else if (step === 'company') { setCompany(inputVal); setInputVal(''); setStep('name') }
    else if (step === 'name') {
      const finalName = inputVal
      setName(finalName)
      setStep('submitting')
      try {
        const body = new FormData()
        body.append('entry.1000020', email)
        body.append('entry.311341703', company)
        body.append('entry.1000022', finalName)
        await fetch(GOOGLE_FORM_ACTION, {
          method: 'POST', body, mode: 'no-cors',
        })
        trackFormSubmit('B')
        setStep('done')
      } catch {
        setStep('error')
      }
    }
  }

  const handleKey = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter') handleNext()
  }

  const history: { who: 'bot' | 'user', text: string }[] = [
    { who: 'bot', text: 'こんにちは。\n無料AI表示診断のお申し込みです。\n3問だけお答えください。' },
  ]
  if (step !== 'email') {
    history.push({ who: 'bot', text: steps.email.bot })
    history.push({ who: 'user', text: email })
  }
  if (step === 'name' || step === 'submitting' || step === 'done' || step === 'error') {
    history.push({ who: 'bot', text: steps.company.bot })
    history.push({ who: 'user', text: company })
  }
  if (step === 'submitting' || step === 'done' || step === 'error') {
    history.push({ who: 'bot', text: steps.name.bot })
    history.push({ who: 'user', text: name })
  }

  const bubbleBot = (text: string, key: string) => (
    <div key={key} style={{ display: 'flex', gap: 8, alignItems: 'flex-end', marginBottom: 12 }}>
      <div style={{
        width: 28, height: 28, borderRadius: '50%', flexShrink: 0,
        background: 'linear-gradient(135deg, #FF2D6B, #C8234F)',
        display: 'flex', alignItems: 'center', justifyContent: 'center',
        fontSize: 16,
      }}>🔍</div>
      <div style={{
        background: 'var(--surface)',
        border: '1px solid rgba(0,0,0,0.08)',
        borderRadius: '4px 16px 16px 16px',
        padding: '10px 14px',
        fontSize: 17, color: 'var(--text)', lineHeight: 1.7,
        maxWidth: '78%',
        whiteSpace: 'pre-wrap',
      }}>{text}</div>
    </div>
  )

  const bubbleUser = (text: string, key: string) => (
    <div key={key} style={{ display: 'flex', justifyContent: 'flex-end', marginBottom: 12 }}>
      <div style={{
        background: 'linear-gradient(135deg, #06C755, #04A044)',
        borderRadius: '16px 4px 16px 16px',
        padding: '10px 14px',
        fontSize: 17, color: 'white', lineHeight: 1.7,
        maxWidth: '78%',
      }}>{text}</div>
    </div>
  )

  return (
    <div style={{
      position: 'fixed', inset: 0, zIndex: 1000,
      background: 'rgba(6,13,31,0.92)', backdropFilter: 'blur(8px)',
      display: 'flex', alignItems: 'center', justifyContent: 'center',
      padding: '16px',
    }}>
      <div style={{
        background: '#F5F5F0',
        width: '100%', maxWidth: 480,
        height: 'auto', maxHeight: '72svh',
        borderRadius: '20px',
        display: 'flex', flexDirection: 'column',
        overflow: 'hidden',
      }}>
        {/* ヘッダー */}
        <div style={{
          display: 'flex', alignItems: 'center', justifyContent: 'space-between',
          padding: '16px 20px',
          background: 'var(--surface)',
          borderBottom: '1px solid rgba(0,0,0,0.08)',
          flexShrink: 0,
        }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
            <div style={{
              width: 36, height: 36, borderRadius: '50%',
              background: 'linear-gradient(135deg, #FF2D6B, #C8234F)',
              display: 'flex', alignItems: 'center', justifyContent: 'center',
              fontSize: 20,
            }}>🔍</div>
            <div>
              <p style={{ fontSize: 17, fontWeight: 800, color: 'var(--text)' }}>AI表示診断</p>
              <p style={{ fontSize: 15, color: '#06C755', fontWeight: 700 }}>● 無料・2営業日以内にお届け</p>
            </div>
          </div>
          <button onClick={onClose} style={{
            background: 'rgba(0,0,0,0.06)', border: 'none',
            color: 'var(--muted)', fontSize: 22, cursor: 'pointer',
            width: 32, height: 32, borderRadius: '50%',
            display: 'flex', alignItems: 'center', justifyContent: 'center',
          }}>×</button>
        </div>

        {/* チャット本文 */}
        <div style={{
          flex: 1, overflowY: 'auto',
          padding: '20px 16px',
          display: 'flex', flexDirection: 'column',
        }}>
          {history.map((h, i) =>
            h.who === 'bot'
              ? bubbleBot(h.text, `h${i}`)
              : bubbleUser(h.text, `h${i}`)
          )}
          {step !== 'submitting' && step !== 'done' && step !== 'error' && (
            bubbleBot(steps[step].bot, 'current')
          )}
          {step === 'submitting' && bubbleBot('送信中です…', 'submitting')}
          {step === 'error' && bubbleBot('通信エラーが発生しました。\nお手数ですが再度お試しください。', 'error')}
          {step === 'done' && (
            <div style={{ textAlign: 'center', padding: '24px 16px' }}>
              <div style={{
                width: 56, height: 56, borderRadius: '50%',
                background: 'linear-gradient(135deg, #06C755, #04A044)',
                display: 'flex', alignItems: 'center', justifyContent: 'center',
                margin: '0 auto 16px',
                boxShadow: '0 8px 24px rgba(6,199,85,0.3)',
              }}>
                <svg width="28" height="28" viewBox="0 0 24 24" fill="none">
                  <path d="M5 13l4 4L19 7" stroke="white" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round"/>
                </svg>
              </div>
              <p style={{ fontSize: 20, fontWeight: 900, color: 'var(--text)', marginBottom: 8 }}>お申し込みありがとうございます</p>
              <p style={{ fontSize: 17, color: 'var(--muted)', lineHeight: 1.8, marginBottom: 24 }}>
                2営業日以内に診断レポートを<br />{email} へお送りします。
              </p>
              <a
                href="https://drive.google.com/uc?export=download&id=1Zl3oZU4ensiPhRD3FckISzUkKs8fvBS0"
                target="_blank" rel="noopener noreferrer"
                style={{
                  display: 'inline-flex', alignItems: 'center', gap: 8,
                  background: 'linear-gradient(135deg, #06C755, #04A044)',
                  color: 'white', textDecoration: 'none',
                  borderRadius: 12, padding: '12px 24px',
                  fontSize: 18, fontWeight: 800,
                  boxShadow: '0 4px 16px rgba(6,199,85,0.3)',
                  marginBottom: 16,
                }}
              >
                <svg width="16" height="16" viewBox="0 0 24 24" fill="none">
                  <path d="M12 16l-4-4h3V4h2v8h3l-4 4z" fill="white"/>
                  <path d="M4 20h16v-2H4v2z" fill="white"/>
                </svg>
                GEO資料をダウンロード（無料）
              </a>
              <div>
                <button onClick={onClose} style={{
                  background: 'none', border: 'none', fontSize: 16,
                  color: 'var(--muted)', cursor: 'pointer', textDecoration: 'underline',
                }}>閉じる</button>
              </div>
            </div>
          )}
        </div>

        {/* 入力エリア */}
        {step !== 'submitting' && step !== 'done' && step !== 'error' && (
          <div style={{
            padding: '12px 16px',
            background: 'var(--surface)',
            borderTop: '1px solid rgba(0,0,0,0.08)',
            display: 'flex', gap: 10, alignItems: 'center',
            flexShrink: 0,
          }}>
            <input
              ref={inputRef}
              type={steps[step].type}
              value={inputVal}
              onChange={e => { setInputVal(e.target.value); setError('') }}
              onKeyDown={handleKey}
              placeholder={steps[step].placeholder}
              style={{
                flex: 1,
                background: '#F0EFEB',
                border: error ? '1.5px solid #FF2D6B' : '1.5px solid transparent',
                borderRadius: 24,
                padding: '10px 16px',
                fontSize: 18, color: 'var(--text)',
                outline: 'none',
              }}
            />
            <button
              onClick={handleNext}
              style={{
                width: 40, height: 40, borderRadius: '50%', flexShrink: 0,
                background: inputVal.trim()
                  ? 'linear-gradient(135deg, #06C755, #04A044)'
                  : 'rgba(0,0,0,0.12)',
                border: 'none', cursor: inputVal.trim() ? 'pointer' : 'default',
                display: 'flex', alignItems: 'center', justifyContent: 'center',
                transition: 'background 0.2s',
              }}
            >
              <svg width="18" height="18" viewBox="0 0 24 24" fill="none">
                <path d="M22 2L11 13M22 2L15 22l-4-9-9-4 20-7z" stroke="white" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/>
              </svg>
            </button>
          </div>
        )}
        {error && (
          <p style={{ fontSize: 15, color: '#FF2D6B', padding: '0 20px 10px', flexShrink: 0 }}>{error}</p>
        )}
      </div>
    </div>
  )
}

// ── AI Brand Icons (SVG) ────────────────────────────────────────────────
function ChatGPTIcon() {
  return (
    <svg width="40" height="40" viewBox="0 0 721 721" fill="none" xmlns="http://www.w3.org/2000/svg" style={{borderRadius: 10, background: '#000'}}>
      <path d="M304.246 295.411V249.828C304.246 245.989 305.687 243.109 309.044 241.191L400.692 188.412C413.167 181.215 428.042 177.858 443.394 177.858C500.971 177.858 537.44 222.482 537.44 269.982C537.44 273.34 537.44 277.179 536.959 281.018L441.954 225.358C436.197 222 430.437 222 424.68 225.358L304.246 295.411ZM518.245 472.945V364.024C518.245 357.304 515.364 352.507 509.608 349.149L389.174 279.096L428.519 256.543C431.877 254.626 434.757 254.626 438.115 256.543L529.762 309.323C556.154 324.679 573.905 357.304 573.905 388.971C573.905 425.436 552.315 459.024 518.245 472.941V472.945ZM275.937 376.982L236.592 353.952C233.235 352.034 231.794 349.154 231.794 345.315V239.756C231.794 188.416 271.139 149.548 324.4 149.548C344.555 149.548 363.264 156.268 379.102 168.262L284.578 222.964C278.822 226.321 275.942 231.119 275.942 237.838V376.986L275.937 376.982ZM360.626 425.922L304.246 394.255V327.083L360.626 295.416L417.002 327.083V394.255L360.626 425.922ZM396.852 571.789C376.698 571.789 357.989 565.07 342.151 553.075L436.674 498.374C442.431 495.017 445.311 490.219 445.311 483.499V344.352L485.138 367.382C488.495 369.299 489.936 372.179 489.936 376.018V481.577C489.936 532.917 450.109 571.785 396.852 571.785V571.789ZM283.134 464.79L191.486 412.01C165.094 396.654 147.343 364.029 147.343 332.362C147.343 295.416 169.415 262.309 203.48 248.393V357.791C203.48 364.51 206.361 369.308 212.117 372.665L332.074 442.237L292.729 464.79C289.372 466.707 286.491 466.707 283.134 464.79ZM277.859 543.48C223.639 543.48 183.813 502.695 183.813 452.314C183.813 448.475 184.294 444.636 184.771 440.797L279.295 495.498C285.051 498.856 290.812 498.856 296.568 495.498L417.002 425.927V471.509C417.002 475.349 415.562 478.229 412.204 480.146L320.557 532.926C308.081 540.122 293.206 543.48 277.854 543.48H277.859ZM396.852 600.576C454.911 600.576 503.37 559.313 514.41 504.612C568.149 490.696 602.696 440.315 602.696 388.976C602.696 355.387 588.303 322.762 562.392 299.25C564.791 289.173 566.231 279.096 566.231 269.024C566.231 200.411 510.571 149.067 446.274 149.067C433.322 149.067 420.846 150.984 408.37 155.305C386.775 134.192 357.026 120.758 324.4 120.758C266.342 120.758 217.883 162.02 206.843 216.721C153.104 230.637 118.557 281.018 118.557 332.357C118.557 365.946 132.95 398.571 158.861 422.083C156.462 432.16 155.022 442.237 155.022 452.309C155.022 520.922 210.682 572.266 274.978 572.266C287.931 572.266 300.407 570.349 312.883 566.028C334.473 587.141 364.222 600.576 396.852 600.576Z" fill="white"/>
    </svg>
  )
}

function GeminiIcon() {
  return (
    <svg width="40" height="40" viewBox="0 0 40 40" fill="none" xmlns="http://www.w3.org/2000/svg">
      <rect width="40" height="40" rx="10" fill="url(#geminiGrad)"/>
      <defs>
        <linearGradient id="geminiGrad" x1="0" y1="0" x2="40" y2="40">
          <stop offset="0%" stopColor="#4285F4"/>
          <stop offset="100%" stopColor="#8B5CF6"/>
        </linearGradient>
      </defs>
      <path d="M20 9 L22.5 17.5 L31 20 L22.5 22.5 L20 31 L17.5 22.5 L9 20 L17.5 17.5 Z" fill="white"/>
    </svg>
  )
}

function PerplexityIcon() {
  return (
    <div style={{
      width: 40, height: 40, borderRadius: 10, overflow: 'hidden',
      background: '#000', flexShrink: 0,
    }}>
      <img src="/perplexity-icon.png" alt="Perplexity" width={40} height={40} style={{ display: 'block' }} />
    </div>
  )
}

function ClaudeIcon() {
  return (
    <div style={{
      width: 40, height: 40, borderRadius: 10,
      background: '#1a1a1a',
      display: 'flex', alignItems: 'center', justifyContent: 'center',
      flexShrink: 0,
    }}>
      <svg height="28" width="28" viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg">
        <path d="M4.709 15.955l4.72-2.647.08-.23-.08-.128H9.2l-.79-.048-2.698-.073-2.339-.097-2.266-.122-.571-.121L0 11.784l.055-.352.48-.321.686.06 1.52.103 2.278.158 1.652.097 2.449.255h.389l.055-.157-.134-.098-.103-.097-2.358-1.596-2.552-1.688-1.336-.972-.724-.491-.364-.462-.158-1.008.656-.722.881.06.225.061.893.686 1.908 1.476 2.491 1.833.365.304.145-.103.019-.073-.164-.274-1.355-2.446-1.446-2.49-.644-1.032-.17-.619a2.97 2.97 0 01-.104-.729L6.283.134 6.696 0l.996.134.42.364.62 1.414 1.002 2.229 1.555 3.03.456.898.243.832.091.255h.158V9.01l.128-1.706.237-2.095.23-2.695.08-.76.376-.91.747-.492.584.28.48.685-.067.444-.286 1.851-.559 2.903-.364 1.942h.212l.243-.242.985-1.306 1.652-2.064.73-.82.85-.904.547-.431h1.033l.76 1.129-.34 1.166-1.064 1.347-.881 1.142-1.264 1.7-.79 1.36.073.11.188-.02 2.856-.606 1.543-.28 1.841-.315.833.388.091.395-.328.807-1.969.486-2.309.462-3.439.813-.042.03.049.061 1.549.146.662.036h1.622l3.02.225.79.522.474.638-.079.485-1.215.62-1.64-.389-3.829-.91-1.312-.329h-.182v.11l1.093 1.068 2.006 1.81 2.509 2.33.127.578-.322.455-.34-.049-2.205-1.657-.851-.747-1.926-1.62h-.128v.17l.444.649 2.345 3.521.122 1.08-.17.353-.608.213-.668-.122-1.374-1.925-1.415-2.167-1.143-1.943-.14.08-.674 7.254-.316.37-.729.28-.607-.461-.322-.747.322-1.476.389-1.924.315-1.53.286-1.9.17-.632-.012-.042-.14.018-1.434 1.967-2.18 2.945-1.726 1.845-.414.164-.717-.37.067-.662.401-.589 2.388-3.036 1.44-1.882.93-1.086-.006-.158h-.055L4.132 18.56l-1.13.146-.487-.456.061-.746.231-.243 1.908-1.312-.006.006z" fill="#D97757" fillRule="nonzero"/>
      </svg>
    </div>
  )
}

// ── CTA Button ───────────────────────────────────────────────────────────
function CTAButton({ onClick, size = 'lg', label, variant = 'B' }: {
  onClick: () => void, size?: 'sm' | 'lg', label?: string, variant?: 'A' | 'B'
}) {
  return (
    <button
      onClick={() => {
        trackModalOpen(variant)
        trackCTAClick(variant, label || 'FV_main_cta')
        onClick()
      }}
      className="cta-btn"
      style={{
        background: 'linear-gradient(135deg, #06C755, #04A044)',
        color: 'white', border: 'none',
        borderRadius: size === 'lg' ? 16 : 12,
        padding: size === 'lg' ? '20px 40px' : '14px 28px',
        fontSize: size === 'lg' ? 18 : 15,
        fontWeight: 800, cursor: 'pointer',
        fontFamily: 'var(--font-noto), sans-serif',
        letterSpacing: '0.02em',
        display: 'inline-flex', alignItems: 'center', justifyContent: 'center', gap: 10, width: '100%',
      }}
    >
      <span>🔍</span>
      <span style={{ textAlign: 'center', lineHeight: 1.5 }}>
        {label
          ? <>
              {label.replace('【診断結果を受け取る】', '')}<br />
              【診断結果を受け取る】
            </>
          : <>なぜ競合はAIに出て、自社は出ないのか<br />【診断結果を受け取る】</>
        }
      </span>
    </button>
  )
}

// ── Main Page ────────────────────────────────────────────────────────────
interface AiscanLP_BProps {
  headline?: {
    area?: string
    industry?: string
  }
}

export default function AiscanLP_B({ headline }: AiscanLP_BProps = {}) {
  const [modalOpen, setModalOpen] = useState(false)
  const [popupVisible, setPopupVisible] = useState(false)
  useABTracking("B")

  // ── ポップアップ表示ロジック ──────────────────────────────────────────
  React.useEffect(() => {
    const COOKIE_KEY = 'geo_popup_closed'
    const closed = document.cookie.split(';').some(c => c.trim().startsWith(COOKIE_KEY + '='))
    if (closed) return

    let shown = false
    const showPopup = () => {
      if (!shown && !modalOpen) {
        shown = true
        setPopupVisible(true)
      }
    }

    // 10秒後に表示
    const timer = setTimeout(showPopup, 10000)

    // 離脱検知（上スクロール）
    let lastScrollY = window.scrollY
    const handleScroll = () => {
      const currentY = window.scrollY
      if (currentY < lastScrollY - 50 && currentY > 100) showPopup()
      lastScrollY = currentY
    }
    window.addEventListener('scroll', handleScroll)

    return () => {
      clearTimeout(timer)
      window.removeEventListener('scroll', handleScroll)
    }
  }, [modalOpen])

  const closePopup = () => {
    setPopupVisible(false)
    // 24時間Cookie
    const expires = new Date(Date.now() + 24 * 60 * 60 * 1000).toUTCString()
    document.cookie = `geo_popup_closed=1; expires=${expires}; path=/`
  }

  return (
    <>
      {modalOpen && <FormModal onClose={() => setModalOpen(false)} variant="B" />}

      {/* ── ポップアップCTA ── */}
      {popupVisible && (
        <div style={{
          position: 'fixed', bottom: 24, left: '50%', transform: 'translateX(-50%)',
          zIndex: 900, width: 'calc(100% - 48px)', maxWidth: 480,
          background: 'var(--surface)',
          border: '1px solid rgba(255,45,107,0.35)',
          borderRadius: 16,
          boxShadow: '0 8px 40px rgba(0,0,0,0.25)',
          padding: '20px 24px',
          display: 'flex', flexDirection: 'column', gap: 12,
        }}>
          <button
            onClick={closePopup}
            style={{
              position: 'absolute', top: 10, right: 12,
              background: 'none', border: 'none',
              color: 'var(--muted)', fontSize: 22,
              cursor: 'pointer', lineHeight: 1,
            }}
          >×</button>
          <p style={{ fontSize: 17, fontWeight: 800, color: 'var(--text)', lineHeight: 1.8, paddingRight: 20, textAlign: 'center' }}>
            このまま閉じますか？<br />
            あなたの会社、GEO対策できていないと<br />
            <span style={{ color: 'var(--accent)' }}>"AIには存在しない企業"のままです。</span>
          </p>
          <CTAButton
            onClick={() => { closePopup(); setModalOpen(true) }}
            size="sm"
            label="無料診断で確認する"
          />
          <p style={{ fontSize: 15, color: 'var(--muted)', fontWeight: 700, textAlign: 'center' }}>
            AIと見込み客にどう認識されているか<br />確認してみてください
          </p>
        </div>
      )}

      {/* ── HEADER ── */}


      {/* ── TICKER ── */}
      <div
        onClick={() => { trackCTAClick('B', 'ticker_cta'); setModalOpen(true) }}
        style={{
          background: 'rgba(200,35,79,0.05)',
          borderBottom: '1px solid rgba(200,35,79,0.12)',
          padding: '10px 0', overflow: 'hidden',
          cursor: 'pointer',
        }}
      >
        <div className="ticker-wrap">
          <div className="ticker-inner" style={{ gap: 60 }}>
            {[...Array(2)].map((_, i) => (
              <div key={i} style={{ display: 'flex', gap: 60, alignItems: 'center' }}>
                {['ChatGPT', 'Gemini', 'Perplexity', 'Claude'].map(ai => (
                  <span key={ai} style={{
                    fontSize: 17, color: 'var(--muted)', whiteSpace: 'nowrap',
                    display: 'flex', alignItems: 'center', gap: 6
                  }}>
                    <span style={{ color: 'var(--accent)', fontSize: 14 }}>●</span>
                    {ai}で検索される時代、あなたの会社は表示されていますか？
                  </span>
                ))}
              </div>
            ))}
          </div>
        </div>
      </div>

      <main>
        {/* ══ S1: FIRST VIEW ══════════════════════════════════════════════ */}
        <section className="noise" style={{
          minHeight: '100svh',
          display: 'flex', alignItems: 'center',
          position: 'relative', overflow: 'hidden',
          padding: '80px 24px',
          background: '#060D1F',
          color: '#F0F4FF',
        }}>
          {/* Full-screen BG image */}
          <div className="fv-bg-b" style={{
            position: 'absolute', inset: 0, zIndex: 0,
            backgroundSize: 'cover',
            backgroundPosition: 'center top',
            backgroundRepeat: 'no-repeat',
          }} />
          {/* Dark overlay */}
          <div style={{
            position: 'absolute', inset: 0, zIndex: 1,
            background: 'linear-gradient(135deg, rgba(6,13,31,0.85) 0%, rgba(6,13,31,0.65) 55%, rgba(6,13,31,0.4) 100%)',
          }} />
          {/* Bottom fade */}
          <div style={{
            position: 'absolute', bottom: 0, left: 0, right: 0, height: 120, zIndex: 2,
            background: 'linear-gradient(to bottom, transparent, var(--bg))',
          }} />

          <div style={{
            maxWidth: 900, margin: '0 auto', width: '100%',
            position: 'relative', zIndex: 3,
            display: 'flex', flexDirection: 'column', alignItems: 'center',
            textAlign: 'center', gap: 32,
          }}>
            {/* Badge */}
            <div className="animate-fadeInUp delay-1" style={{
              display: 'inline-flex', alignItems: 'center', gap: 8,
              background: 'rgba(255,45,107,0.1)',
              border: '1px solid rgba(255,45,107,0.4)',
              borderRadius: 100, padding: '6px 16px',
            }}>
              <span style={{ width: 8, height: 8, borderRadius: '50%', background: '#FF2D6B', display: 'inline-block' }} />
              <span style={{ fontSize: 17, color: '#FF8AAD', fontWeight: 600 }}>
                経営者・マーケティング責任者様へ
              </span>
            </div>

            {/* Main headline */}
            <div className="animate-fadeInUp delay-2">
              <h1 style={{
                fontSize: 'clamp(28px, 5.5vw, 56px)',
                fontWeight: 900, lineHeight: 1.3,
                letterSpacing: '-0.02em',
                textWrap: 'balance',
              } as React.CSSProperties}>
                {headline?.area && headline?.industry ? (
                  // エリア×業種ページ
                  <>
                    <span style={{ color: '#FFFFFF' }}>
                      「{headline.area}」で
                    </span>
                    <span className="gradient-text">
                      "おすすめ{headline.industry === '__none__' ? '' : headline.industry}"
                    </span>
                    <span style={{ color: '#FFFFFF' }}>
                      に選ばれない会社を、
                    </span>
                    <br />
                    <span style={{ color: '#FFFFFF' }}>
                      AI検索で
                    </span>
                    <span className="gradient-text">
                      3ヶ月以内に露出させる
                    </span>
                    <span style={{ color: '#FFFFFF' }}>
                      GEO対策
                    </span>
                  </>
                ) : headline?.industry ? (
                  // 業種のみページ
                  <>
                    <span style={{ color: '#FFFFFF' }}>
                      AI検索で
                    </span>
                    <span className="gradient-text">
                      "おすすめ{headline.industry === '__none__' ? '' : headline.industry}"
                    </span>
                    <span style={{ color: '#FFFFFF' }}>
                      に選ばれない会社を、
                    </span>
                    <br />
                    <span className="gradient-text">
                      3ヶ月以内に露出させる
                    </span>
                    <span style={{ color: '#FFFFFF' }}>
                      GEO対策
                    </span>
                  </>
                ) : (
                  // デフォルト（ルートLP・B案コピー）
                  <>
                    <span style={{ color: '#FFFFFF', display: 'block' }}>
                      AI検索で競合は
                    </span>
                    <span style={{ color: '#FFFFFF', display: 'block' }}>
                      推薦されているのに、
                    </span>
                    <span className="gradient-text" style={{ display: 'block' }}>
                      あなたの会社だけが「存在しない」
                    </span>
                    <span style={{ color: '#FFFFFF', display: 'block' }}>
                      ことになっていませんか？
                    </span>
                  </>
                )}
              </h1>
            </div>

            {/* Sub copy */}
            <p className="animate-fadeInUp delay-3" style={{
              fontSize: 'clamp(18px, 2vw, 22px)',
              color: '#FFFFFF', fontWeight: 700, lineHeight: 1.8,
              maxWidth: 600,
              textWrap: 'balance',
            } as React.CSSProperties}>
              これからの顧客はAIに聞いて商品を選びます。<br />
              <strong style={{ color: '#FFFFFF' }}>手遅れになる前に、自社のAIからの「見え方」を<br />把握しましょう。</strong>
            </p>

            {/* CTA */}
            <div className="animate-fadeInUp delay-4" style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 12, width: '100%', maxWidth: 480 }}>
              <p style={{ fontSize: 17, color: '#FF8AAD', fontWeight: 700 }}>
                ↓ 競合との差を今すぐ確認する ↓
              </p>
              <CTAButton onClick={() => setModalOpen(true)} variant="B" />
              <p style={{ fontSize: 17, color: '#FFFFFF', fontWeight: 700 }}>
                診断レポート＋GEO資料を無料でお届けします
              </p>
              <p style={{ fontSize: 16, color: 'rgba(255,255,255,0.75)', lineHeight: 1.6, fontWeight: 700 }}>
                ※競合他社の出現状況も合わせて診断可能です
              </p>
            </div>

            {/* AI logos */}
            <div
              className="animate-fadeInUp delay-4"
              onClick={() => { trackCTAClick('B', 'ai_logos_cta'); setModalOpen(true) }}
              style={{
                display: 'flex', gap: 20, flexWrap: 'wrap', justifyContent: 'center',
                marginTop: 8,
                cursor: 'pointer',
                padding: '12px 20px',
                borderRadius: 16,
                border: '1px solid rgba(255,255,255,0.1)',
                background: 'rgba(255,255,255,0.05)',
              }}
            >
              {[
                { icon: <ChatGPTIcon />, label: 'ChatGPT' },
                { icon: <GeminiIcon />, label: 'Gemini' },
                { icon: <PerplexityIcon />, label: 'Perplexity' },
                { icon: <ClaudeIcon />, label: 'Claude' },
              ].map(({ icon, label }) => (
                <div key={label} style={{
                  display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 6,
                }}>
                  {icon}
                  <span style={{ fontSize: 16, color: '#FFFFFF', fontWeight: 700 }}>{label}</span>
                </div>
              ))}
            </div>
          </div>
        </section>

        {/* ══ NEW-S2: RESULTS（事例セクション） ════════════════════════ */}
        <section style={{ padding: '80px 20px', background: 'var(--bg)' }}>
          <div style={{ maxWidth: 900, margin: '0 auto' }}>

            {/* ① ヘッドコピー */}
            <div style={{ textAlign: 'center', marginBottom: 56 }}>
              <p style={{ color: 'var(--accent)', fontSize: 18, fontWeight: 700, letterSpacing: '0.12em', marginBottom: 12 }}>
                RESULTS
              </p>
              <h2 style={{ fontSize: 'clamp(24px, 5vw, 38px)', fontWeight: 900, lineHeight: 1.45, color: 'var(--text)', marginBottom: 16 }}>
                AI検索における&ldquo;推薦有無&rdquo;が、<br />集客格差を生んでいます。
              </h2>
              <p style={{ fontSize: 'clamp(17px, 3vw, 20px)', color: 'var(--muted)', lineHeight: 1.7 }}>
                実際の検索結果ベースで、対策の有無による差分を公開します。
              </p>
            </div>

            {/* ② CASEカード */}
            <div style={{ background: 'var(--surface)', border: '1px solid rgba(0,0,0,0.06)', borderRadius: 16, padding: '32px 28px', marginBottom: 32 }}>
              <p style={{ fontSize: 14, color: 'var(--muted)', fontWeight: 700, letterSpacing: '0.1em', marginBottom: 20 }}>
                CASE — 「恵比寿 地下バー」ChatGPT検索結果
              </p>

              {/* 画像2枚 縦配列 */}
              <div style={{ display: 'flex', flexDirection: 'column', gap: 20, marginBottom: 24 }}>
                {/* HP画像 */}
                <div style={{ borderRadius: 12, overflow: 'hidden', border: '1px solid rgba(0,0,0,0.08)' }}>
                  <div style={{ background: '#111', padding: '8px 12px', display: 'flex', alignItems: 'center', gap: 6 }}>
                    {['#ff5f57','#febc2e','#28c840'].map(c => (
                      <span key={c} style={{ width: 8, height: 8, borderRadius: '50%', background: c, display: 'inline-block' }} />
                    ))}
                    <span style={{ fontSize: 14, color: '#888', marginLeft: 6 }}>barsecret.tokyo</span>
                  </div>
                  <img src="/case-secret-hp.png" alt="Bar SECRET 公式サイト" style={{ width: '100%', display: 'block', maxHeight: 360, objectFit: 'cover' }} />
                  <div style={{ padding: '10px 12px', background: '#fafafa', borderTop: '1px solid rgba(0,0,0,0.06)' }}>
                    <p style={{ fontSize: 15, color: 'var(--muted)', fontWeight: 700 }}>🌐 対象店舗 HP — Bar SECRET</p>
                  </div>
                </div>

                {/* ChatGPT画像（ホバー＋クリック拡大） */}
                <div
                  onClick={() => {
                    const el = document.getElementById('results-lightbox')
                    if (el) { el.style.display = 'flex'; document.body.style.overflow = 'hidden' }
                  }}
                  style={{
                    borderRadius: 12, overflow: 'hidden', border: '1px solid rgba(0,0,0,0.08)',
                    cursor: 'zoom-in', transition: 'transform 0.2s ease, box-shadow 0.2s ease, border-color 0.2s ease',
                  }}
                  onMouseEnter={e => {
                    const el = e.currentTarget as HTMLDivElement
                    el.style.transform = 'translateY(-4px) scale(1.02)'
                    el.style.boxShadow = '0 12px 40px rgba(0,0,0,0.16)'
                    el.style.borderColor = 'rgba(255,45,107,0.3)'
                  }}
                  onMouseLeave={e => {
                    const el = e.currentTarget as HTMLDivElement
                    el.style.transform = ''
                    el.style.boxShadow = ''
                    el.style.borderColor = 'rgba(0,0,0,0.08)'
                  }}
                >
                  <div style={{ background: '#111', padding: '8px 12px', display: 'flex', alignItems: 'center', gap: 6 }}>
                    {['#ff5f57','#febc2e','#28c840'].map(c => (
                      <span key={c} style={{ width: 8, height: 8, borderRadius: '50%', background: c, display: 'inline-block' }} />
                    ))}
                    <span style={{ fontSize: 14, color: '#888', marginLeft: 6 }}>chatgpt.com</span>
                  </div>
                  <img src="/case-chatgpt-bar.png" alt="ChatGPT 恵比寿 地下バー 検索結果" style={{ width: '100%', display: 'block', maxHeight: 360, objectFit: 'cover', objectPosition: 'top' }} />
                  <div style={{ padding: '10px 12px', background: '#fafafa', borderTop: '1px solid rgba(0,0,0,0.06)' }}>
                    <p style={{ fontSize: 15, color: 'var(--muted)', fontWeight: 700 }}>🤖 ChatGPT検索結果 — 実名で推薦表示</p>
                  </div>
                </div>
              </div>

              {/* ライトボックス */}
              <div
                id="results-lightbox"
                onClick={() => {
                  const el = document.getElementById('results-lightbox')
                  if (el) { el.style.display = 'none'; document.body.style.overflow = '' }
                }}
                style={{ display: 'none', position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.85)', zIndex: 9999, alignItems: 'center', justifyContent: 'center', padding: 24, cursor: 'zoom-out' }}
              >
                <img src="/case-chatgpt-bar.png" alt="ChatGPT検索結果 拡大" style={{ maxWidth: '90vw', maxHeight: '90vh', objectFit: 'contain', borderRadius: 12, boxShadow: '0 24px 80px rgba(0,0,0,0.5)' }} />
              </div>

              {/* 対象店舗情報 */}
              <div style={{ background: 'rgba(0,0,0,0.03)', borderRadius: 10, padding: '14px 16px', marginBottom: 20, border: '1px solid rgba(0,0,0,0.05)' }}>
                <p style={{ fontSize: 16, color: 'var(--muted)', marginBottom: 6 }}>
                  対象店舗：<strong style={{ color: 'var(--text)' }}>Bar SECRET</strong>
                  <span style={{ color: 'var(--muted)', fontSize: 15, marginLeft: 6 }}>(東京・恵比寿)</span>
                </p>
                <p style={{ fontSize: 16, color: 'var(--muted)' }}>→「おすすめ」として推薦表示を獲得</p>
              </div>

              {/* VOICE */}
              <div style={{ background: 'linear-gradient(135deg, rgba(255,45,107,0.06) 0%, rgba(120,60,200,0.06) 100%)', border: '1px solid rgba(255,45,107,0.18)', borderRadius: 12, padding: '20px 18px', marginBottom: 24 }}>
                <p style={{ fontSize: 15, color: 'var(--accent)', fontWeight: 700, letterSpacing: '0.1em', marginBottom: 12 }}>VOICE</p>
                <p style={{ fontSize: 'clamp(18px, 3vw, 20px)', fontWeight: 800, color: 'var(--text)', lineHeight: 1.6, marginBottom: 12 }}>
                  「流入ではなく、意思決定の質が変わった」
                </p>
                <p style={{ fontSize: 'clamp(16px, 2.5vw, 18px)', color: 'var(--muted)', lineHeight: 1.95 }}>
                  従来飲食系ポータルサイトやSNSでの発信でしかPRを行なっておらず、来店頂くお客様との会話の中からAIの発展スピードを痛感させられていたところ、GEO対策のお話を頂き、HPリニューアルと同時にGEO対策を施しました。<br /><br />
                  GEO対策を施してから僅か2週間足らずで「ChatGPTを見てきたんですけど」というお客様が来店。この反応スピードには大変驚きました。<br /><br />
                  激戦区でもある東京・恵比寿のバーでもGEO対策を施すと新規集客に繋がるという事が実証できた事、この激戦区・恵比寿の地で集客チャネルが手に入った事、大変感謝しております。
                </p>
              </div>

              {/* 実績サマリー 3カラム */}
              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 12 }}>
                {[
                  { label: '施策', value: 'HP＋GEO', sub: '2026年4月' },
                  { label: '結果', value: 'AI推薦表示', sub: '獲得' },
                  { label: '反応', value: '来店発生', sub: 'ChatGPT経由' },
                ].map((item, i) => (
                  <div key={i} style={{ background: 'var(--bg)', borderRadius: 10, padding: '16px 12px', textAlign: 'center', border: '1px solid rgba(0,0,0,0.06)' }}>
                    <p style={{ fontSize: 13, color: 'var(--muted)', letterSpacing: '0.08em', marginBottom: 6 }}>{item.label}</p>
                    <p style={{ fontSize: 'clamp(16px, 3vw, 20px)', fontWeight: 900, color: 'var(--accent)', lineHeight: 1.2, marginBottom: 4 }}>{item.value}</p>
                    <p style={{ fontSize: 13, color: 'var(--muted)' }}>{item.sub}</p>
                  </div>
                ))}
              </div>
            </div>

            {/* ④ Before / After 画像 */}
            <div style={{ marginBottom: 32 }}>
              <p style={{ fontSize: 17, fontWeight: 800, color: 'var(--text)', marginBottom: 16, textAlign: 'center' }}>
                同一条件での検索結果比較
              </p>
              <img
                src="/geo-before-after.png"
                alt="GEO対策 Before / After 検索結果比較"
                style={{ width: '100%', borderRadius: 12, border: '1px solid rgba(0,0,0,0.08)', display: 'block' }}
              />
              <p style={{ textAlign: 'center', fontSize: 'clamp(17px, 3vw, 20px)', fontWeight: 800, color: 'var(--text)', marginTop: 20, lineHeight: 1.7 }}>
                「存在しない状態」から<br />「意思決定に関与する状態」へ
              </p>
            </div>

            {/* ⑤ 非対策店舗との比較 */}
            <div style={{ background: 'var(--surface)', border: '1px solid rgba(0,0,0,0.06)', borderRadius: 16, padding: '28px', marginBottom: 32 }}>
              <p style={{ fontSize: 20, fontWeight: 800, color: 'var(--text)', marginBottom: 20, textAlign: 'center' }}>
                同一エリアでも、推薦有無で露出は分かれます
              </p>
              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12 }}>
                <div style={{ background: 'rgba(0,200,100,0.06)', border: '1px solid rgba(0,180,90,0.2)', borderRadius: 10, padding: '16px 14px' }}>
                  <p style={{ fontSize: 18, fontWeight: 700, color: '#00a86b', marginBottom: 10 }}>GEO対策あり</p>
                  {['店名が表示される', '文脈で紹介される', '来店導線が成立'].map((t, i) => (
                    <p key={i} style={{ fontSize: 20, color: 'var(--text)', lineHeight: 1.7 }}>✓ {t}</p>
                  ))}
                </div>
                <div style={{ background: 'rgba(255,45,107,0.05)', border: '1px solid rgba(255,45,107,0.18)', borderRadius: 10, padding: '16px 14px' }}>
                  <p style={{ fontSize: 18, fontWeight: 700, color: 'var(--accent)', marginBottom: 10 }}>GEO対策なし</p>
                  {['店名が出ない', '抽象カテゴリ扱い', '導線が存在しない'].map((t, i) => (
                    <p key={i} style={{ fontSize: 20, color: 'var(--muted)', lineHeight: 1.7 }}>✗ {t}</p>
                  ))}
                </div>
              </div>
            </div>

            {/* RESULTS CTA */}
            <div style={{ textAlign: 'center', marginTop: 48, padding: '0 20px' }}>
              <CTAButton onClick={() => setModalOpen(true)} />
              <p style={{ fontSize: 15, color: 'var(--muted)', marginTop: 10, fontWeight: 700 }}>
                ✓ 完全無料　✓ 営業電話なし　✓ 2営業日以内にお届け
              </p>
            </div>
          </div>
        </section>

        {/* ══ S3: REALITY CHECK（短縮・損失訴求） ════════════════════ */}
        <section style={{ padding: '64px 20px', background: '#000000', borderTop: 'none', position: 'relative', overflow: 'hidden' }}>
          {/* Dark overlay */}
          <div style={{
            position: 'absolute', inset: 0, zIndex: 1,
            background: 'linear-gradient(135deg, rgba(6,13,31,1.0) 0%, rgba(6,13,31,0.85) 55%, rgba(6,13,31,0.6) 100%)',
          }} />
          {/* Content */}
          <div style={{ position: 'relative', zIndex: 2, width: '100%' }}>
          <div style={{ maxWidth: 640, margin: '0 auto' }}>
            <div style={{ textAlign: 'center', marginBottom: 32 }}>
              <p style={{ color: 'var(--accent)', fontSize: 18, fontWeight: 700, letterSpacing: '0.12em', marginBottom: 10 }}>
                REALITY CHECK
              </p>
              <h2 style={{ fontSize: 'clamp(28px, 4vw, 44px)', fontWeight: 900, lineHeight: 1.4, color: '#FFFFFF' }}>
                このままだと起きる損失
              </h2>
            </div>
            <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
              {[
                'AI検索での競合露出が続き、指名機会を失い続ける',
                '広告費をかけても「AI非推薦」状態は変わらない',
                '対策が遅れるほど、競合との格差は広がる',
              ].map((item, i) => (
                <div key={i} style={{ display: 'flex', alignItems: 'flex-start', gap: 12, background: 'rgba(255,255,255,0.06)', border: '1px solid rgba(255,45,107,0.3)', borderRadius: 10, padding: '14px 16px' }}>
                  <span style={{ color: 'var(--accent)', fontWeight: 900, fontSize: 20, flexShrink: 0, marginTop: 1 }}>!</span>
                  <span style={{ fontSize: 'clamp(20px, 3vw, 22px)', color: '#FFFFFF', lineHeight: 1.65 }}>{item}</span>
                </div>
              ))}
            </div>
          </div>
          </div>{/* /Content */}
        </section>

        {/* ══ S6: なぜ今？ ═════════════════════════════════════════════ */}
        <section style={{ padding: '100px 24px', background: 'var(--bg)' }}>
          <div style={{ maxWidth: 800, margin: '0 auto', textAlign: 'center' }}>
            <p style={{ color: 'var(--accent)', fontSize: 18, fontWeight: 700, marginBottom: 12, letterSpacing: '0.1em' }}>
              WHY NOW
            </p>
            <h2 style={{ fontSize: 'clamp(28px, 4vw, 44px)', fontWeight: 900, marginBottom: 20 }}>
              この変化は、もう始まっています
            </h2>
            <p style={{ color: 'var(--muted)', fontSize: 20, lineHeight: 1.8, marginBottom: 60 }}>
              検索の主役が静かに交代しています。
            </p>

            <div style={{ display: 'flex', flexDirection: 'column', gap: 16, marginBottom: 60 }}>
              {[
                { from: 'Google検索', to: 'AI検索', arrow: true },
                { from: 'MEO・比較サイト', to: 'AI推薦', arrow: true },
                { from: 'SEO・MEO', to: 'GEO', arrow: true },
              ].map(({ from, to }) => (
                <div key={from} style={{
                  display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 20,
                  background: 'var(--surface)',
                  border: '1px solid rgba(0,0,0,0.07)',
                  borderRadius: 12, padding: '18px 28px',
                }}>
                  <span style={{ fontSize: 22, color: 'var(--muted)', minWidth: 120, textAlign: 'right' }}>{from}</span>
                  <span style={{ color: 'var(--accent)', fontSize: 24 }}>→</span>
                  <span style={{ fontSize: 22, fontWeight: 800, color: 'var(--text)', minWidth: 120, textAlign: 'left' }}>{to}</span>
                </div>
              ))}
            </div>

            <div style={{
              background: 'rgba(245,166,35,0.08)',
              border: '1px solid rgba(245,166,35,0.25)',
              borderRadius: 16, padding: '28px 32px',
            }}>
              <p style={{ fontSize: 'clamp(22px, 2.5vw, 28px)', fontWeight: 800, lineHeight: 1.6 }}>
                <span className="gradient-text-gold">早い会社から順に、席が埋まっていきます。</span>
              </p>
            </div>
          </div>
        </section>

        {/* ══ DIAGNOSIS PREVIEW（WHY NOW直後に移動） ════════════════════ */}
        <section style={{ padding: '100px 24px', background: 'var(--bg)' }}>
          <div style={{ maxWidth: 900, margin: '0 auto' }}>
            <div style={{ textAlign: 'center', marginBottom: 60 }}>
              <p style={{ color: 'var(--accent)', fontSize: 18, fontWeight: 700, marginBottom: 12, letterSpacing: '0.1em' }}>
                DIAGNOSIS PREVIEW
              </p>
              <h2 style={{ fontSize: 'clamp(28px, 4vw, 44px)', fontWeight: 900, lineHeight: 1.3 }}>
                診断すると、<span className="gradient-text">こう見えます</span>
              </h2>
              <p style={{ color: 'var(--muted)', marginTop: 16, fontSize: 20 }}>
                4つのAIエンジンで、あなたの会社の認識状況を可視化します
              </p>
            </div>
            <div style={{
              background: 'rgba(255,45,107,0.04)',
              border: '1px solid rgba(255,45,107,0.15)',
              borderRadius: 16, padding: '20px 24px',
              marginBottom: 16,
            }}>
              <p style={{ fontSize: 17, color: 'var(--accent)', fontWeight: 700, marginBottom: 12, letterSpacing: '0.08em' }}>
                ▼ 実際の診断結果イメージ（競合他社の場合）
              </p>
              <div style={{
                display: 'grid',
                gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))',
                gap: 12, marginBottom: 16,
              }}>
                <DiagnosisCard ai="ChatGPT" icon={<ChatGPTIcon />} result="圏外" detail="おすすめ企業リストに非掲載" color="#FF6B6B" />
                <DiagnosisCard ai="Gemini" icon={<GeminiIcon />} result="言及なし" detail="競合3社のみ回答" color="#FF6B6B" />
                <DiagnosisCard ai="Perplexity" icon={<PerplexityIcon />} result="競合のみ引用" detail="自社への言及ゼロ" color="#FF6B6B" />
                <DiagnosisCard ai="Claude" icon={<ClaudeIcon />} result="情報不足" detail="企業認識が不完全" color="#F5A623" />
              </div>
              <div style={{
                background: 'rgba(255,45,107,0.08)',
                borderRadius: 8, padding: '12px 16px',
                display: 'flex', alignItems: 'center', gap: 10,
              }}>
                <span style={{ fontSize: 24 }}>⚠️</span>
                <p style={{ fontSize: 18, color: '#FF8AAD', fontWeight: 600, lineHeight: 1.5 }}>
                  この状態では、AIに「おすすめ企業」を聞いた顧客に<br />
                  <strong style={{ color: 'var(--accent)' }}>あなたの会社は存在しないも同然です。</strong>
                </p>
              </div>
            </div>
            <div style={{ textAlign: 'center' }}>
              <CTAButton onClick={() => setModalOpen(true)} label="AI検索での自社の現在地を知る＋レポートプレゼント【診断結果を受け取る】" />
              <p style={{ fontSize: 16, color: 'var(--muted)', marginTop: 12, lineHeight: 1.6, fontWeight: 700 }}>
                診断結果では、"現在AIに推薦されている企業"が表示されます
              </p>
            </div>
          </div>
        </section>

        <div className="section-divider" />

        {/* ══ S2.7: HOW IT WORKS ════════════════════════════════════════ */}
        <section style={{ padding: '80px 20px', background: 'transparent', position: 'relative', overflow: 'hidden' }}>
          {/* BG image */}
          <div className="fv-bg-b" style={{
            position: 'absolute', inset: 0, zIndex: 0,
            backgroundSize: 'cover',
            backgroundPosition: 'center top',
            backgroundRepeat: 'no-repeat',
          }} />
          {/* Dark overlay */}
          <div style={{
            position: 'absolute', inset: 0, zIndex: 1,
            background: 'linear-gradient(135deg, rgba(6,13,31,1.0) 0%, rgba(6,13,31,0.85) 55%, rgba(6,13,31,0.6) 100%)',
          }} />
          {/* Content */}
          <div style={{ position: 'relative', zIndex: 2, width: '100%' }}>
          <div style={{ maxWidth: 640, margin: '0 auto' }}>
            <div style={{ textAlign: 'center', marginBottom: 48 }}>
              <p style={{
                color: 'var(--accent)', fontSize: 20, fontWeight: 700,
                letterSpacing: '0.12em', marginBottom: 12,
              }}>
                HOW IT WORKS
              </p>
              <h2 style={{
                fontSize: 'clamp(26px, 5vw, 38px)',
                fontWeight: 900, lineHeight: 1.45, color: '#FFFFFF', marginBottom: 14,
              }}>
                なぜ、AIに推薦される状態を<br />再現できるのか？
              </h2>
              <p style={{ fontSize: 'clamp(19px, 3vw, 21px)', color: 'rgba(255,255,255,0.7)', lineHeight: 1.7 }}>
                属人的なノウハウではなく、"構造"で設計しています。
              </p>
            </div>

            {/* ステップ */}
            <div style={{ display: 'flex', flexDirection: 'column', gap: 0 }}>
              {[
                {
                  step: '01',
                  label: 'STEP1：設計（検索意図の占有）',
                  items: ['「恵比寿 地下バー」のような検索意図を分解', '"どんな文脈で紹介されるべきか"を定義'],
                  point: 'キーワードではなく「意味単位」で設計',
                },
                {
                  step: '02',
                  label: 'STEP2：最適化（AIに理解させる）',
                  items: ['HP構造の再設計（見出し・文脈・情報配置）', 'AIが引用しやすい文章構造へ最適化'],
                  point: '人間向けSEOではなく「AI向け構造化」',
                },
                {
                  step: '03',
                  label: 'STEP3：接続（外部整合性）',
                  items: ['外部媒体（Google / SNS / 地図情報）との統一', '情報の一貫性を担保'],
                  point: '情報のズレ＝評価低下',
                },
              ].map(({ step, label, items, point }, i, arr) => (
                <div key={i} style={{ display: 'flex', gap: 0 }}>
                  {/* 左：ステップライン */}
                  <div style={{
                    display: 'flex', flexDirection: 'column', alignItems: 'center',
                    width: 48, flexShrink: 0,
                  }}>
                    <div style={{
                      width: 36, height: 36, borderRadius: '50%',
                      background: 'linear-gradient(135deg, #FF2D6B, #C8234F)',
                      display: 'flex', alignItems: 'center', justifyContent: 'center',
                      flexShrink: 0,
                    }}>
                      <span style={{ fontSize: 19, color: '#fff', fontWeight: 900 }}>{step}</span>
                    </div>
                    {i < arr.length - 1 && (
                      <div style={{
                        width: 2, flex: 1, minHeight: 24,
                        background: 'rgba(255,45,107,0.2)',
                        margin: '4px 0',
                      }} />
                    )}
                  </div>
                  {/* 右：内容 */}
                  <div style={{
                    flex: 1, paddingLeft: 14,
                    paddingBottom: i < arr.length - 1 ? 32 : 0,
                  }}>
                    <p style={{ fontSize: 23, fontWeight: 800, color: '#FFFFFF', marginBottom: 10 }}>{label}</p>
                    <div style={{ marginBottom: 10 }}>
                      {items.map((item, j) => (
                        <p key={j} style={{ fontSize: 20, color: 'rgba(255,255,255,0.8)', lineHeight: 1.75 }}>・{item}</p>
                      ))}
                    </div>
                    <div style={{
                      display: 'inline-flex', alignItems: 'center', gap: 6,
                      background: 'rgba(255,255,255,0.06)', border: '1px solid rgba(255,255,255,0.12)',
                      borderRadius: 8, padding: '6px 12px',
                    }}>
                      <span style={{ fontSize: 18, color: 'rgba(255,255,255,0.85)', fontWeight: 700 }}>👉 {point}</span>
                    </div>
                  </div>
                </div>
              ))}
            </div>

            {/* 実績テキスト */}
            <div style={{
              marginTop: 40, textAlign: 'center',
              background: 'rgba(255,255,255,0.06)', border: '1px solid rgba(255,255,255,0.12)',
              borderRadius: 12, padding: '18px 20px',
            }}>
              <p style={{ fontSize: 20, color: 'rgba(255,255,255,0.85)', lineHeight: 1.7, fontWeight: 700 }}>
                実際にこの設計で、Bar SECRETは推薦表示を獲得しています
              </p>
            </div>

            {/* CTA */}
            <div style={{ marginTop: 36, textAlign: 'center' }}>
              <CTAButton onClick={() => setModalOpen(true)} />
              <p style={{ fontSize: 16, color: 'rgba(255,255,255,0.8)', marginTop: 10, fontWeight: 700 }}>
                ✓ 完全無料　✓ 営業電話なし　✓ 2営業日以内にお届け
              </p>
            </div>
          </div>
          </div>{/* /Content */}
        </section>

        {/* ══ S2.8: WHY HARD TO REPLICATE（統合版） ═════════════════════ */}
        <section style={{ padding: '100px 20px', background: '#000000', position: 'relative', overflow: 'hidden' }}>
          {/* Grid decoration */}
          <div style={{
            position: 'absolute', inset: 0, zIndex: 0,
            backgroundImage: 'linear-gradient(rgba(255,45,107,0.04) 1px, transparent 1px), linear-gradient(90deg, rgba(255,45,107,0.04) 1px, transparent 1px)',
            backgroundSize: '60px 60px', pointerEvents: 'none',
          }} />
          <div style={{
            position: 'absolute', top: -200, right: -200, width: 600, height: 600, zIndex: 0,
            background: 'radial-gradient(circle, rgba(255,45,107,0.06) 0%, transparent 70%)',
            pointerEvents: 'none',
          }} />
          <div style={{ position: 'relative', zIndex: 1, maxWidth: 900, margin: '0 auto' }}>

            {/* Head */}
            <div style={{ marginBottom: 52 }}>
              <p style={{ fontSize: 13, fontWeight: 700, letterSpacing: '0.14em', color: 'var(--accent)', marginBottom: 14, textTransform: 'uppercase' }}>
                WHY HARD TO REPLICATE
              </p>
              <h2 style={{ fontSize: 'clamp(26px, 4.5vw, 40px)', fontWeight: 900, lineHeight: 1.45, color: '#FFFFFF', marginBottom: 18 }}>
                なぜ、この施策は<br />他社が再現しづらいのか？
              </h2>
              <p style={{ fontSize: 'clamp(16px, 2.5vw, 19px)', color: 'rgba(255,255,255,0.6)', lineHeight: 1.75 }}>
                見えている"施策"ではなく、見えていない"設計"が結果を分けます。
              </p>
            </div>

            {/* 3層設計カラム */}
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 20, marginBottom: 48 }}
              className="geo-3col">
              {[
                { num: 'LAYER 01', title: '文脈設計', body: 'どの検索意図に対して、どのポジションで認識されるかを定義' },
                { num: 'LAYER 02', title: '意味構造', body: '情報を"単語"ではなく"意味単位"で整理し、AIに正しく理解させる' },
                { num: 'LAYER 03', title: '出力最適化', body: 'AIが回答を生成する際に"採用される表現"へ調整' },
              ].map(({ num, title, body }, i) => (
                <div key={i} style={{
                  background: 'rgba(255,255,255,0.04)', border: '1px solid rgba(255,255,255,0.1)',
                  borderTop: '2px solid var(--accent)', borderRadius: 12, padding: '28px 24px',
                }}>
                  <p style={{ fontSize: 11, fontWeight: 700, letterSpacing: '0.14em', color: 'var(--accent)', marginBottom: 10, textTransform: 'uppercase' }}>{num}</p>
                  <p style={{ fontSize: 'clamp(17px, 2.5vw, 20px)', fontWeight: 800, color: '#FFFFFF', marginBottom: 12, lineHeight: 1.4 }}>{title}</p>
                  <p style={{ fontSize: 'clamp(13px, 1.8vw, 15px)', color: 'rgba(255,255,255,0.6)', lineHeight: 1.75 }}>{body}</p>
                </div>
              ))}
            </div>

            {/* 一般 vs 本サービス */}
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 20, marginBottom: 48 }}
              className="geo-2col">
              <div style={{
                background: 'rgba(255,255,255,0.03)', border: '1px solid rgba(255,255,255,0.08)',
                borderRadius: 12, padding: '28px 24px',
              }}>
                <p style={{ fontSize: 12, fontWeight: 700, letterSpacing: '0.12em', color: 'rgba(255,255,255,0.5)', textTransform: 'uppercase', marginBottom: 14 }}>
                  一般的な施策
                </p>
                <p style={{ fontSize: 'clamp(14px, 2vw, 16px)', color: 'rgba(255,255,255,0.5)', lineHeight: 1.75 }}>
                  キーワード・コンテンツ量・SEOのレイヤーで止まる。「後から調整」を前提に設計。
                </p>
              </div>
              <div style={{
                background: 'rgba(255,45,107,0.07)', border: '1px solid rgba(255,45,107,0.25)',
                borderRadius: 12, padding: '28px 24px',
              }}>
                <p style={{ fontSize: 12, fontWeight: 700, letterSpacing: '0.12em', color: 'var(--accent)', textTransform: 'uppercase', marginBottom: 14 }}>
                  本サービス
                </p>
                <p style={{ fontSize: 'clamp(14px, 2vw, 16px)', color: 'rgba(255,255,255,0.85)', lineHeight: 1.75 }}>
                  「最初にズレない構造を作る」ことに特化。表面的な模倣では同じ結果にならない。
                </p>
              </div>
            </div>

            {/* Authority */}
            <div style={{
              background: 'rgba(255,255,255,0.03)', border: '1px solid rgba(255,255,255,0.12)',
              borderLeft: '3px solid var(--accent)', borderRadius: '0 12px 12px 0', padding: '28px 32px', marginBottom: 48,
            }}>
              <p style={{ fontSize: 12, fontWeight: 700, letterSpacing: '0.14em', color: 'rgba(255,255,255,0.5)', textTransform: 'uppercase', marginBottom: 16 }}>
                AUTHORITY BASIS
              </p>
              <p style={{ fontSize: 'clamp(15px, 2vw, 17px)', color: 'rgba(255,255,255,0.8)', lineHeight: 1.85, marginBottom: 20 }}>
                本設計は、Google公式プログラムで体系化された知見をベースに構築しています。<br />
                単なる施策ではなく、「AIの出力構造」を前提に設計されています。
              </p>
              <div style={{ display: 'flex', gap: 20, alignItems: 'center', flexWrap: 'wrap' }}>
                <div style={{
                  background: 'rgba(255,255,255,0.05)', border: '1px solid rgba(255,255,255,0.1)',
                  borderRadius: 12, padding: '12px 16px', display: 'flex', alignItems: 'center', gap: 14,
                }}>
                  {/* eslint-disable-next-line @next/next/no-img-element */}
                  <img src="/google-prompting-essentials_1.png" alt="Google Prompting Essentials" style={{ width: 64, height: 64, objectFit: 'contain', filter: 'brightness(0.85) contrast(1.1)' }} />
                  <div>
                    <p style={{ fontSize: 11, color: 'rgba(255,255,255,0.5)', letterSpacing: '0.1em', marginBottom: 4 }}>GOOGLE / COURSERA</p>
                    <p style={{ fontSize: 14, fontWeight: 700, color: '#FFFFFF', lineHeight: 1.4 }}>Google Prompting<br />Essentials</p>
                  </div>
                </div>
                <div style={{
                  background: 'rgba(255,255,255,0.05)', border: '1px solid rgba(255,255,255,0.1)',
                  borderRadius: 12, padding: '12px 16px', display: 'flex', alignItems: 'center', gap: 14,
                }}>
                  {/* eslint-disable-next-line @next/next/no-img-element */}
                  <img src="/google-ai-essentials-v1.png" alt="Google AI Essentials" style={{ width: 64, height: 64, objectFit: 'contain' }} />
                  <div>
                    <p style={{ fontSize: 11, color: 'rgba(255,255,255,0.5)', letterSpacing: '0.1em', marginBottom: 4 }}>GOOGLE / COURSERA</p>
                    <p style={{ fontSize: 14, fontWeight: 700, color: '#FFFFFF', lineHeight: 1.4 }}>Google AI<br />Essentials</p>
                  </div>
                </div>
              </div>
            </div>

            {/* Final message */}
            <p style={{
              fontSize: 'clamp(18px, 3vw, 22px)', fontWeight: 800, color: '#FFFFFF', lineHeight: 1.65,
              paddingLeft: 20, position: 'relative',
            }}>
              <span style={{ position: 'absolute', left: 0, top: 6, bottom: 6, width: 3, background: 'var(--accent)', borderRadius: 2 }} />
              「知識」ではなく「構造理解」に依存するため、<br />表面的な模倣では再現できません。
            </p>
          </div>
        </section>

        <div className="section-divider" />

        {/* ══ S7: FINAL CTA ════════════════════════════════════════════ */}
        <section style={{
          padding: '120px 24px',
          background: `radial-gradient(ellipse 80% 60% at 50% 100%, rgba(160,0,110,0.3) 0%, transparent 70%), var(--bg)`,
          textAlign: 'center',
        }}>
          <div style={{ maxWidth: 700, margin: '0 auto' }}>
            <h2 style={{ fontSize: 'clamp(22px, 4vw, 40px)', fontWeight: 900, lineHeight: 1.3, marginBottom: 20, whiteSpace: 'nowrap' }}>
              まずは、<span className="gradient-text">現状を確認してください</span>
            </h2>
            <p style={{ color: 'var(--muted)', fontSize: 22, lineHeight: 1.8, marginBottom: 48 }}>
              診断レポートとGEO資料を無料でお届けします。<br />
              競合が先に席を取る前に、まず現状を確認してください。
            </p>

            <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 16 }}>
              <CTAButton onClick={() => setModalOpen(true)} />
              <div style={{ display: 'flex', gap: 24, flexWrap: 'wrap', justifyContent: 'center' }}>
                {['✓ 診断レポート無料', '✓ GEO資料プレゼント', '✓ 営業なし'].map(item => (
                  <span key={item} style={{ fontSize: 17, color: 'var(--muted)' }}>{item}</span>
                ))}
              </div>
              <p style={{ fontSize: 16, color: 'var(--muted)', lineHeight: 1.6, fontWeight: 700 }}>
                診断結果では、"現在AIに推薦されている企業"が表示されます
              </p>
            </div>
          </div>
        </section>
      </main>

      {/* ── FOOTER ── */}
      <footer style={{
        background: '#000000',
        borderTop: '1px solid rgba(255,255,255,0.08)',
        padding: '48px 24px 32px',
        textAlign: 'center',
      }}>
        <p style={{ fontSize: 17, fontWeight: 700, marginBottom: 8, color: '#FFFFFF' }}>GEO Search Protocol</p>
        <p style={{ fontSize: 15, color: 'rgba(255,255,255,0.6)', marginBottom: 24 }}>
          <a href="https://www.coaretail.com" target="_blank" rel="noopener noreferrer"
            style={{ color: 'rgba(255,255,255,0.6)', textDecoration: 'none' }}>
            合同会社コア・リテール（CoaRetail G.K.）
          </a>
        </p>

        {/* 内部リンク */}
        <div style={{
          display: 'flex', flexWrap: 'wrap', justifyContent: 'center', gap: '8px 24px',
          marginBottom: 24,
          paddingBottom: 24,
          borderBottom: '1px solid rgba(255,255,255,0.12)',
        }}>
          {[
            { label: 'GEOとは？', href: 'https://www.coaretail.com/geo' },
            { label: 'GEOの定義と仕組み', href: 'https://www.coaretail.com/geo-definition' },
            { label: 'GEO対策会社とは', href: 'https://www.coaretail.com/geo-company' },
            { label: 'GEOホワイトペーパー', href: 'https://www.coaretail.com/geo-whitepaper', hidden: true },
          ].map(({ label, href, hidden }) => (
            <a key={label} href={href} target="_blank" rel="noopener noreferrer"
              style={{ fontSize: 15, color: 'rgba(255,255,255,0.6)', textDecoration: 'none', ...(hidden ? { position: 'absolute', width: 1, height: 1, overflow: 'hidden', opacity: 0, pointerEvents: 'none' } : {}) }}>
              {label}
            </a>
          ))}
        </div>

        <a href="https://www.coaretail.com/lp_privacy" target="_blank" rel="noopener noreferrer"
          style={{ fontSize: 14, color: 'rgba(255,255,255,0.6)', textDecoration: 'none', display: 'inline-block', marginBottom: 8 }}>
          プライバシーポリシー
        </a>
        <p style={{ fontSize: 14, color: 'rgba(255,255,255,0.6)' }}>
          © 2026 CoaRetail G.K. All rights reserved.
        </p>
      </footer>
    </>
  )
}
