import type { Config } from 'tailwindcss'

const config: Config = {
  content: ['./src/**/*.{ts,tsx,md}'],
  theme: { extend: {} },
  plugins: [require('@tailwindcss/typography')],
}

export default config
