document.addEventListener('DOMContentLoaded', function() {
  const rows = [
    {
      name: '株式会社No.1',
      badge: 'おすすめ',
      fee: '1％〜15%',
      speed: '最短即日',
      speedFast: false,
      rate: '90%以上',
      target: '法人・個人事業主',
      feature: '最大1億円まで対応可能',
      ctaUrl: 'https://px.a8.net/svt/ejp?a8mat=4B1G9M+5KN56Q+4EKW+5YJRM',
      ctaText: '無料相談する',
      types: ['large', 'individual'] // 1億円対応・個人事業主OK
    },
    {
      name: 'ジャパンマネジメント',
      badge: '',
      fee: '10%〜20％',
      speed: '最短即日',
      speedFast: false,
      rate: '90%以上',
      target: '法人・個人事業主',
      feature: '最大5000万円まで対応可能',
      ctaUrl: 'https://px.a8.net/svt/ejp?a8mat=4B1G9M+5L8KSI+3V6A+5YJRM',
      ctaText: '無料相談する',
      types: ['large'] // 5000万円対応・手数料高めで他には非該当
    },
    {
      name: '株式会社アクシアプラス',
      badge: 'おすすめ',
      fee: '4%〜',
      speed: '最短即日',
      speedFast: false,
      rate: '90%以上',
      target: '法人のみ',
      feature: '土日祝日・平日時間外の振込も対応',
      ctaUrl: 'https://px.a8.net/svt/ejp?a8mat=3N82JP+4YM3SY+4HV8+5YJRM',
      ctaText: '無料相談する',
      types: ['fast'] // 土日祝・時間外対応でスピード重視
    },
    {
      name: 'PayToday',
      badge: '',
      fee: '1％〜9.5%',
      speed: '最短即日',
      speedFast: false,
      rate: '90%以上',
      target: '法人・個人事業主',
      feature: '低手数料・少額から対応（10万円〜）',
      ctaUrl: 'https://px.a8.net/svt/ejp?a8mat=3N83C4+6J6A9U+4OPW+5YRHE',
      ctaText: '無料相談する',
      types: ['low', 'individual'] // 手数料1%〜・10万円〜
    },
    {
      name: '株式会社トラストゲートウェイ',
      badge: '',
      fee: '1％〜9.5%',
      speed: '最短即日',
      speedFast: false,
      rate: '90%以上',
      target: '法人・個人事業主',
      feature: '医療系法人の診療報酬債権の買取も対応',
      ctaUrl: 'https://px.a8.net/svt/ejp?a8mat=3N82JP+4Z7JEQ+3RD2+5YJRM',
      ctaText: '無料相談する',
      types: ['industry', 'low'] // 医療特化・手数料1%〜
    },
    {
      name: '株式会社トップ・マネジメント',
      badge: 'おすすめ',
      fee: '3.5％〜12.5%',
      speed: '最短即日',
      speedFast: false,
      rate: '90%以上',
      target: '法人・個人事業主',
      feature: '高額対応（1億円以上）・大企業向け',
      ctaUrl: 'https://px.a8.net/svt/ejp?a8mat=3N83C4+A6R2YQ+3JLM+63H8I',
      ctaText: '無料相談する',
      types: ['large'] // 1億円以上・大企業向け
    },
    {
      name: '株式会社エスコム',
      badge: 'おすすめ',
      fee: '1.5％〜12%',
      speed: '最短即日',
      speedFast: false,
      rate: '90%以上',
      target: '法人のみ',
      feature: '低手数料・少額から対応（30万円〜）',
      ctaUrl: 'https://px.a8.net/svt/ejp?a8mat=3N83C4+6JRPVM+4OCA+60OXE',
      ctaText: '無料相談する',
      types: ['low'] // 手数料1.5%〜・法人のみなので individual 除外
    },
    {
      name: '株式会社ネクストワン',
      badge: '',
      fee: '1.5％〜10%',
      speed: '最短即日',
      speedFast: false,
      rate: '90%以上',
      target: '法人のみ',
      feature: '高額対応（1億円以上）・大企業向け',
      ctaUrl: 'https://px.a8.net/svt/ejp?a8mat=3N82JP+50EEMA+4OCU+609HU',
      ctaText: '無料相談する',
      types: ['large'] // 1億円以上・法人のみ
    },
    {
      name: '株式会社西日本ファクター',
      badge: '',
      fee: '2.8%〜',
      speed: '最短即日',
      speedFast: false,
      rate: '88%以上',
      target: '法人のみ',
      feature: '福岡中心に九州・四国地方に強い。',
      ctaUrl: 'https://px.a8.net/svt/ejp?a8mat=3N81RK+6NCBIA+3XT0+5YJRM',
      ctaText: '無料相談する',
      types: ['industry'] // 地域特化（九州・四国）
    },
    {
      name: 'えんナビ',
      badge: '',
      fee: '5%〜',
      speed: '最短即日',
      speedFast: false,
      rate: '88%以上',
      target: '法人・個人事業主',
      feature: '最大5000万円まで対応可能',
      ctaUrl: 'https://px.a8.net/svt/ejp?a8mat=3N81RK+6LK0OY+44CA+5YJRM',
      ctaText: '無料相談する',
      types: ['individual'] // 個人事業主OK・他は特筆なし
    },
    {
      name: 'うりかけ堂',
      badge: 'おすすめ',
      fee: '2%〜',
      speed: '最短2時間',
      speedFast: true,
      rate: '97%以上',
      target: '法人・個人事業主',
      feature: '低手数料・少額から対応（10万円〜）',
      ctaUrl: 'https://px.a8.net/svt/ejp?a8mat=3N81RK+6JRPVM+4S8A+5YJRM',
      ctaText: '無料相談する',
      types: ['fast', 'low', 'audit', 'individual'] // 最短2時間・手数料2%〜・審査97%・個人OK
    },
    {
      name: 'QuQuMo',
      badge: 'おすすめ',
      fee: '1％〜14.8%',
      speed: '最短2時間',
      speedFast: true,
      rate: '90%以上',
      target: '法人・個人事業主',
      feature: '低手数料・少額から対応（5万円〜）',
      ctaUrl: 'https://px.a8.net/svt/ejp?a8mat=3N81RK+6IKUO2+4JGG+BWVTE',
      ctaText: '無料相談する',
      types: ['fast', 'low', 'individual'] // 最短2時間・手数料1%〜・5万円〜
    },
    {
      name: 'ファクタリングゼロ',
      badge: 'おすすめ',
      fee: '1.5％〜10%',
      speed: '最短即日',
      speedFast: false,
      rate: '90%以上',
      target: '法人・個人事業主',
      feature: '西日本地域限定。最大5000万円まで対応可能',
      ctaUrl: 'https://px.a8.net/svt/ejp?a8mat=4B1G9M+5XQOHU+4DJO+5YJRM',
      ctaText: '無料相談する',
      types: ['industry', 'individual'] // 西日本地域特化・個人事業主OK
    },
  ];

  // ===== 比較テーブル生成 =====
  const tbody = document.getElementById('compare-tbody');
  if (tbody) {
    tbody.innerHTML = rows.map(r => `
      <tr>
        <td class="company-name"><a href="${r.ctaUrl}" target="_blank">${r.name}</a>${r.badge ? '<span class="badge-recommend">'+r.badge+'</span>' : ''}</td>
        <td>${r.fee}</td>
        <td>${r.speedFast ? '<span class="badge-fast">'+r.speed+'</span>' : r.speed}</td>
        <td>${r.rate}</td>
        <td>${r.target}</td>
        <td>${r.feature}</td>
        <td class="cta-cell"><a href="${r.ctaUrl}" target="_blank">${r.ctaText}</a></td>
      </tr>
    `).join('');
  }

  // ===== タイプ別おすすめカード生成 =====
  const TYPE_CONFIG = [
    {
      key: 'fast',
      icon: '🚀',
      label: 'とにかく急ぎ',
      desc: '今日中に資金が必要。スピード最優先で選びたい方。'
    },
    {
      key: 'low',
      icon: '💰',
      label: '手数料を抑えたい',
      desc: 'コストを最小化したい。繰り返し利用を検討中の方。'
    },
    {
      key: 'audit',
      icon: '⚠️',
      label: '審査が不安',
      desc: '赤字・税滞納・債務超過などで審査が心配な方。'
    },
    {
      key: 'large',
      icon: '🏢',
      label: '高額・大口',
      desc: '1,000万円以上の大口取引。法人・上場企業向け。'
    },
    {
      key: 'industry',
      icon: '🏥',
      label: '業種・地域特化',
      desc: '医療・建設・特定地域など専門領域の売掛金を現金化したい方。'
    },
    {
      key: 'individual',
      icon: '👤',
      label: '個人事業主',
      desc: 'フリーランス・個人事業主で少額から利用したい方。'
    },
  ];

  const typeGrid = document.getElementById('type-grid');
  if (typeGrid) {
    typeGrid.innerHTML = TYPE_CONFIG.map(cfg => {
      const matched = rows.filter(r => r.types && r.types.includes(cfg.key));
      // badgeありを優先、最大3社まで表示
      const sorted = [
        ...matched.filter(r => r.badge),
        ...matched.filter(r => !r.badge)
      ].slice(0, 3);

      const recHtml = sorted.length
        ? sorted.map(r =>
            `<a href="${r.ctaUrl}" target="_blank" class="type-card-rec-link">
              <span class="type-card-rec-badge">おすすめ</span>${r.name}
            </a>`
          ).join('')
        : '<span class="type-card-rec-none">－</span>';

      return `
        <div class="type-card">
          <div class="type-card-head">${cfg.icon} ${cfg.label}</div>
          <div class="type-card-body">
            <p>${cfg.desc}</p>
            <div class="type-card-recs">${recHtml}</div>
          </div>
        </div>
      `;
    }).join('');
  }
});
