document.addEventListener('DOMContentLoaded', function() {
    const rows = [
      {
        name: '株式会社No.1',
        badge: 'おすすめ', // または空文字
        fee: '1％〜15%',
        speed: '最短即日',
        speedFast: false,
        rate: '90%以上',
        target: '法人・個人事業主',
        feature: '最大1億円まで対応可能',
        ctaUrl: 'https://px.a8.net/svt/ejp?a8mat=4B1G9M+5KN56Q+4EKW+5YJRM',
        ctaText: '無料相談する'
      },
      //
      {
        name: 'ジャパンマネジメント',
        badge: '', // または空文字
        fee: '10%〜20％',
        speed: '最短即日',
        speedFast: false,
        rate: '90%以上',
        target: '法人・個人事業主',
        feature: '最大5000万円まで対応可能',
        ctaUrl: 'https://px.a8.net/svt/ejp?a8mat=4B1G9M+5L8KSI+3V6A+5YJRM',
        ctaText: '無料相談する'
      },
      //
      {
        name: '株式会社アクシアプラス',
        badge: 'おすすめ', // または空文字
        fee: '4%〜',
        speed: '最短即日',
        speedFast: false,
        rate: '90%以上',
        target: '法人のみ',
        feature: '土日祝日・平日時間外の振込も対応',
        ctaUrl: 'https://px.a8.net/svt/ejp?a8mat=3N82JP+4YM3SY+4HV8+5YJRM',
        ctaText: '無料相談する'
      },
      //
      {
        name: 'PayToday',
        badge: '', // または空文字
        fee: '1％〜9.5%',
        speed: '最短即日',
        speedFast: false,
        rate: '90%以上',
        target: '法人・個人事業主',
        feature: '低手数料・少額から対応（10万円〜）',
        ctaUrl: 'https://px.a8.net/svt/ejp?a8mat=3N83C4+6J6A9U+4OPW+5YRHE',
        ctaText: '無料相談する'
      },
      //
      {
        name: '株式会社トラストゲートウェイ',
        badge: '', // または空文字
        fee: '1％〜9.5%',
        speed: '最短即日',
        speedFast: false,
        rate: '90%以上',
        target: '法人・個人事業主',
        feature: '医療系法人の診療報酬債権の買取も対応',
        ctaUrl: 'https://px.a8.net/svt/ejp?a8mat=3N82JP+4Z7JEQ+3RD2+5YJRM',
        ctaText: '無料相談する'
      },
      //
      {
        name: '株式会社トップ・マネジメント',
        badge: 'おすすめ', // または空文字
        fee: '3.5％〜12.5%',
        speed: '最短即日',
        speedFast: false,
        rate: '90%以上',
        target: '法人・個人事業主',
        feature: '高額対応（1億円以上）・大企業向け',
        ctaUrl: 'https://px.a8.net/svt/ejp?a8mat=3N83C4+A6R2YQ+3JLM+63H8I',
        ctaText: '無料相談する'
      },
      //
      {
        name: '株式会社エスコム',
        badge: 'おすすめ', // または空文字
        fee: '1.5％〜12%',
        speed: '最短即日',
        speedFast: false,
        rate: '90%以上',
        target: '法人のみ',
        feature: '低手数料・少額から対応（30万円〜）',
        ctaUrl: 'https://px.a8.net/svt/ejp?a8mat=3N83C4+6JRPVM+4OCA+60OXE',
        ctaText: '無料相談する'
      },
      //
      {
        name: '株式会社ネクストワン',
        badge: '', // または空文字
        fee: '1.5％〜10%',
        speed: '最短即日',
        speedFast: false,
        rate: '90%以上',
        target: '法人のみ',
        feature: '高額対応（1億円以上）・大企業向け',
        ctaUrl: 'https://px.a8.net/svt/ejp?a8mat=3N82JP+50EEMA+4OCU+609HU',
        ctaText: '無料相談する'
      },
      //
      {
        name: '株式会社西日本ファクター',
        badge: '', // または空文字
        fee: '2.8%〜',
        speed: '最短即日',
        speedFast: false,
        rate: '88%以上',
        target: '法人のみ',
        feature: '福岡中心に九州・四国地方に強い。',
        ctaUrl: 'https://px.a8.net/svt/ejp?a8mat=3N81RK+6NCBIA+3XT0+5YJRM',
        ctaText: '無料相談する'
      },
      //
      {
        name: 'えんナビ',
        badge: '', // または空文字
        fee: '5%〜',
        speed: '最短即日',
        speedFast: false,
        rate: '88%以上',
        target: '法人・個人事業主',
        feature: '最大5000万円まで対応可能',
        ctaUrl: 'https://px.a8.net/svt/ejp?a8mat=3N81RK+6LK0OY+44CA+5YJRM',
        ctaText: '無料相談する'
      },
      //
      {
        name: 'うりかけ堂',
        badge: 'おすすめ', // または空文字
        fee: '2%〜',
        speed: '最短2時間',
        speedFast: true,
        rate: '97%以上',
        target: '法人・個人事業主',
        feature: '低手数料・少額から対応（10万円〜）',
        ctaUrl: 'https://px.a8.net/svt/ejp?a8mat=3N81RK+6JRPVM+4S8A+5YJRM',
        ctaText: '無料相談する'
      },
      //
      {
        name: 'QuQuMo',
        badge: 'おすすめ', // または空文字
        fee: '1％〜14.8%',
        speed: '最短2時間',
        speedFast: true,
        rate: '90%以上',
        target: '法人・個人事業主',
        feature: '低手数料・少額から対応（5万円〜）',
        ctaUrl: 'https://px.a8.net/svt/ejp?a8mat=3N81RK+6IKUO2+4JGG+BWVTE',
        ctaText: '無料相談する'
      },
      //
      {
        name: 'ファクタリングゼロ',
        badge: 'おすすめ', // または空文字
        fee: '1.5％〜10%',
        speed: '最短即日',
        speedFast: false,
        rate: '90%以上',
        target: '法人・個人事業主',
        feature: '西日本地域限定。最大5000万円まで対応可能',
        ctaUrl: 'https://px.a8.net/svt/ejp?a8mat=4B1G9M+5XQOHU+4DJO+5YJRM',
        ctaText: '無料相談する'
      },
      //
    ];
    
    const tbody = document.getElementById('compare-tbody');
    tbody.innerHTML = rows.map(r => `
      <tr>
        <td class="company-name">${r.name}${r.badge ? '<span class="badge-recommend">'+r.badge+'</span>' : ''}</td>
        <td>${r.fee}</td>
        <td>${r.speedFast ? '<span class="badge-fast">'+r.speed+'</span>' : r.speed}</td>
        <td>${r.rate}</td>
        <td>${r.target}</td>
        <td>${r.feature}</td>
        <td class="cta-cell"><a href="${r.ctaUrl}" target="_blank">${r.ctaText}</a></td>
      </tr>
    `).join('');
  });