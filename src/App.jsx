import { useState, useEffect, useCallback, useRef } from "react";

const WATCHLIST = [
  'AGTUSDT','PLUMEUSDT','PHAUSDT','INUSDT','GENIUSUSDT','NILUSDT',
  'VVVUSDT','BSBUSDT','HANAUSDT','BANUSDT','GMTUSDT','COSUSDT',
  'BILLUSDT','UBUSDT','MEUSDT','EDENUSDT','PLAYUSDT','FIDAUSDT',
  'CHZUSDT','ALLOUSDT','SANTOSUSDT','GUAUSDT','AINUSDT'
];

const BASE = 'https://fapi.binance.com';
const sleep = ms => new Promise(r => setTimeout(r, ms));

function calcBBWidth(closes, period = 20) {
  if (closes.length < period) return null;
  const slice = closes.slice(-period);
  const mean = slice.reduce((a, b) => a + b, 0) / period;
  const std = Math.sqrt(slice.reduce((a, b) => a + (b - mean) ** 2, 0) / period);
  return mean > 0 ? (4 * std) / mean : null;
}

function scoreSignals(klines, fundingRate, markPrice, lastPrice) {
  if (!klines || klines.length < 22) return { score: 0, maxScore: 14, signals: [], direction: 'UNKNOWN', bias: 0 };
  const closes  = klines.map(k => parseFloat(k[4]));
  const volumes = klines.map(k => parseFloat(k[5]));
  const highs   = klines.map(k => parseFloat(k[2]));
  const lows    = klines.map(k => parseFloat(k[3]));
  const opens   = klines.map(k => parseFloat(k[1]));
  const signals = []; let score = 0; let bias = 0;

  // 1. Volume Compression
  const avgVol20  = volumes.slice(-21,-1).reduce((a,b)=>a+b,0)/20;
  const recentAvg = volumes.slice(-4,-1).reduce((a,b)=>a+b,0)/3;
  const compRatio = avgVol20>0 ? recentAvg/avgVol20 : 1;
  if (compRatio<0.30){score+=2;signals.push({id:'VC',label:'Vol compressed',detail:`${(compRatio*100).toFixed(0)}% of avg`,weight:2,cls:'neutral'});}
  else if(compRatio<0.55){score+=1;signals.push({id:'VC',label:'Vol tightening',detail:`${(compRatio*100).toFixed(0)}% of avg`,weight:1,cls:'neutral'});}

  // 2. Volume Spike
  const lastVol=volumes[volumes.length-1];
  const spikeR=avgVol20>0?lastVol/avgVol20:0;
  if(spikeR>=4){score+=2;signals.push({id:'VS',label:'VOL SPIKE',detail:`${spikeR.toFixed(1)}x avg`,weight:2,cls:'alert'});bias+=closes[closes.length-1]>opens[opens.length-1]?2:-2;}
  else if(spikeR>=2.2){score+=1;signals.push({id:'VS',label:'Vol building',detail:`${spikeR.toFixed(1)}x avg`,weight:1,cls:'caution'});bias+=closes[closes.length-1]>opens[opens.length-1]?1:-1;}

  // 3. Funding Rate
  const fr=parseFloat(fundingRate||0)*100;
  if(Math.abs(fr)>=0.15){score+=2;signals.push({id:'FR',label:'Funding extreme',detail:`${fr>0?'+':''}${fr.toFixed(4)}%`,weight:2,cls:fr<0?'bull':'bear'});bias+=fr<0?2:-2;}
  else if(Math.abs(fr)>=0.07){score+=1;signals.push({id:'FR',label:'Funding elevated',detail:`${fr>0?'+':''}${fr.toFixed(4)}%`,weight:1,cls:fr<0?'bull':'bear'});bias+=fr<0?1:-1;}

  // 4. BB Squeeze
  const curBBW=calcBBWidth(closes,20);
  if(curBBW!==null){
    const hw=[];
    for(let i=20;i<closes.length-1;i++){const w=calcBBWidth(closes.slice(0,i+1),20);if(w!==null)hw.push(w);}
    if(hw.length>=3){
      const avgHW=hw.reduce((a,b)=>a+b,0)/hw.length;
      const sq=curBBW/avgHW;
      if(sq<0.35){score+=2;signals.push({id:'BB',label:'BB squeeze extreme',detail:`${(sq*100).toFixed(0)}% width`,weight:2,cls:'neutral'});}
      else if(sq<0.55){score+=1;signals.push({id:'BB',label:'BB squeezing',detail:`${(sq*100).toFixed(0)}% width`,weight:1,cls:'neutral'});}
    }
  }

  // 5. Price Coiling
  const l5H=Math.max(...highs.slice(-5)),l5L=Math.min(...lows.slice(-5));
  const l5R=closes.length>5?(l5H-l5L)/closes[closes.length-1]*100:999;
  const p5H=Math.max(...highs.slice(-10,-5)),p5L=Math.min(...lows.slice(-10,-5));
  const p5R=closes.length>10?(p5H-p5L)/closes[closes.length-6]*100:999;
  if(p5R>0&&l5R<p5R*0.35){score+=2;signals.push({id:'CO',label:'Price coiling',detail:`${l5R.toFixed(2)}% range`,weight:2,cls:'neutral'});}
  else if(p5R>0&&l5R<p5R*0.55){score+=1;signals.push({id:'CO',label:'Range narrowing',detail:`${l5R.toFixed(2)}% range`,weight:1,cls:'neutral'});}

  // 6. Mark/Last Spread
  if(markPrice&&lastPrice&&parseFloat(lastPrice)>0){
    const sp=(parseFloat(markPrice)-parseFloat(lastPrice))/parseFloat(lastPrice)*100;
    if(Math.abs(sp)>=0.5){score+=2;signals.push({id:'SP',label:'Mark/Last diverge',detail:`${sp>0?'+':''}${sp.toFixed(3)}%`,weight:2,cls:sp>0?'bull':'bear'});bias+=sp>0?2:-2;}
    else if(Math.abs(sp)>=0.2){score+=1;signals.push({id:'SP',label:'Mark/Last spread',detail:`${sp>0?'+':''}${sp.toFixed(3)}%`,weight:1,cls:sp>0?'bull':'bear'});bias+=sp>0?1:-1;}
  }

  // 7. Candle Pattern
  const last=closes.length-1;
  const bodies=closes.map((c,i)=>Math.abs(c-opens[i])/closes[i]*100);
  const l3tiny=bodies.slice(-4,-1).every(b=>b<0.4);
  const lc=closes[last]-opens[last];
  const lb=Math.abs(lc)/closes[last]*100;
  if(l3tiny&&lb>0.8){score+=2;signals.push({id:'CP',label:'Coil→Engulfing',detail:lc>0?'Bullish break':'Bearish break',weight:2,cls:lc>0?'bull':'bear'});bias+=lc>0?2:-2;}
  else if(l3tiny){score+=1;signals.push({id:'CP',label:'3 doji coil',detail:'Breakout pending',weight:1,cls:'neutral'});}

  let direction='WATCH';
  if(score>=4){if(bias>0)direction='PUMP';else if(bias<0)direction='DUMP';else direction='COILING';}
  return {score,maxScore:14,signals,direction,bias};
}

const fmtVol=v=>v>=1e9?`${(v/1e9).toFixed(1)}B`:v>=1e6?`${(v/1e6).toFixed(0)}M`:`${(v/1e3).toFixed(0)}K`;
const fmtP=p=>p<0.0001?p.toExponential(3):p<0.01?p.toFixed(6):p<1?p.toFixed(5):p<100?p.toFixed(3):p.toFixed(2);

export default function App(){
  const [coins,setCoins]=useState([]);
  const [loading,setLoading]=useState(false);
  const [progress,setProgress]=useState(0);
  const [lastScan,setLastScan]=useState(null);
  const [tab,setTab]=useState('all');
  const [expanded,setExpanded]=useState(null);
  const [autoScan,setAutoScan]=useState(false);
  const [error,setError]=useState(null);
  const [countdown,setCountdown]=useState(300);
  const autoRef=useRef(null);
  const cntRef=useRef(null);

  const runScan=useCallback(async()=>{
    setLoading(true);setProgress(5);setError(null);
    try{
      const [tickers,premiums]=await Promise.all([
        fetch(`${BASE}/fapi/v1/ticker/24hr`).then(r=>r.json()),
        fetch(`${BASE}/fapi/v1/premiumIndex`).then(r=>r.json()),
      ]);
      setProgress(20);
      const fMap={},mMap={};
      premiums.forEach(p=>{fMap[p.symbol]=p.lastFundingRate;mMap[p.symbol]=p.markPrice;});
      const SKIP=new Set(['BUSDUSDT','USDCUSDT','TUSDUSDT','FDUSDUSDT','USDPUSDT']);
      const perps=tickers.filter(t=>t.symbol.endsWith('USDT')&&!SKIP.has(t.symbol)&&parseFloat(t.quoteVolume)>500000);
      const wSet=new Set(WATCHLIST);
      const byAbs=[...perps].sort((a,b)=>Math.abs(parseFloat(b.priceChangePercent))-Math.abs(parseFloat(a.priceChangePercent)));
      const seen=new Set();const cands=[];
      for(const t of [...WATCHLIST.map(s=>perps.find(x=>x.symbol===s)).filter(Boolean),...byAbs]){
        if(!seen.has(t.symbol)&&cands.length<50){seen.add(t.symbol);cands.push(t);}
      }
      setProgress(30);
      const results=[];
      for(let i=0;i<cands.length;i+=8){
        const batch=cands.slice(i,i+8);
        const bd=await Promise.all(batch.map(async t=>{
          try{
            const kl=await fetch(`${BASE}/fapi/v1/klines?symbol=${t.symbol}&interval=5m&limit=27`).then(r=>r.json());
            const {score,maxScore,signals,direction,bias}=scoreSignals(kl,fMap[t.symbol],mMap[t.symbol],t.lastPrice);
            return{symbol:t.symbol,base:t.symbol.replace('USDT',''),price:parseFloat(t.lastPrice),
              change24h:parseFloat(t.priceChangePercent),volume:parseFloat(t.quoteVolume),
              fundingRate:parseFloat(fMap[t.symbol]||0)*100,markPrice:parseFloat(mMap[t.symbol]||t.lastPrice),
              score,maxScore,signals,direction,bias,isWatch:wSet.has(t.symbol)};
          }catch{return null;}
        }));
        results.push(...bd.filter(Boolean));
        setProgress(30+((i+8)/cands.length)*65);
        if(i+8<cands.length)await sleep(120);
      }
      results.sort((a,b)=>b.score-a.score);
      setCoins(results);setLastScan(new Date());setProgress(100);setCountdown(300);
    }catch(e){setError(`API error: ${e.message}`);}
    finally{setLoading(false);}
  },[]);

  useEffect(()=>{runScan();},[]);

  useEffect(()=>{
    if(autoScan){
      autoRef.current=setInterval(runScan,5*60*1000);
      cntRef.current=setInterval(()=>setCountdown(c=>c>0?c-1:300),1000);
    }else{clearInterval(autoRef.current);clearInterval(cntRef.current);}
    return()=>{clearInterval(autoRef.current);clearInterval(cntRef.current);};
  },[autoScan,runScan]);

  const filtered=coins.filter(c=>{
    if(tab==='watchlist')return c.isWatch;
    if(tab==='pump')return c.direction==='PUMP'&&c.score>=4;
    if(tab==='dump')return c.direction==='DUMP'&&c.score>=4;
    if(tab==='hot')return c.score>=6;
    return true;
  });

  const hotN=coins.filter(c=>c.score>=6).length;
  const pumpN=coins.filter(c=>c.direction==='PUMP'&&c.score>=4).length;
  const dumpN=coins.filter(c=>c.direction==='DUMP'&&c.score>=4).length;

  const clsColor={bull:'#00ff88',bear:'#ff4466',neutral:'#00ccff',caution:'#ffaa00',alert:'#ff44ff'};
  const clsBg={bull:'rgba(0,255,136,0.08)',bear:'rgba(255,68,102,0.08)',neutral:'rgba(0,200,255,0.06)',caution:'rgba(255,170,0,0.08)',alert:'rgba(255,68,255,0.08)'};

  return(
    <div style={{background:'#060a0f',minHeight:'100vh',fontFamily:"'JetBrains Mono','Courier New',monospace",color:'#c8d8e8',position:'relative'}}>
      <style>{`
        @import url('https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;600;700&display=swap');
        @keyframes spin{to{transform:rotate(360deg)}}
        @keyframes pulse{0%,100%{opacity:1}50%{opacity:0.3}}
        @keyframes glow{0%,100%{text-shadow:0 0 6px rgba(255,68,102,0.6)}50%{text-shadow:0 0 16px rgba(255,68,102,1)}}
        .crow:hover{background:rgba(0,255,136,0.03)!important;cursor:pointer}
        .sbtn:hover{background:rgba(0,255,136,0.12)!important;box-shadow:0 0 14px rgba(0,255,136,0.3)}
        ::-webkit-scrollbar{width:4px}
        ::-webkit-scrollbar-thumb{background:rgba(0,255,136,0.2);border-radius:2px}
        .hot-glow{animation:glow 1.8s ease-in-out infinite}
      `}</style>

      {/* Grid bg */}
      <div style={{position:'fixed',inset:0,pointerEvents:'none',zIndex:0,
        backgroundImage:'linear-gradient(rgba(0,255,136,0.025) 1px,transparent 1px),linear-gradient(90deg,rgba(0,255,136,0.025) 1px,transparent 1px)',
        backgroundSize:'44px 44px'}}/>

      {/* Progress */}
      <div style={{position:'fixed',top:0,left:0,height:'2px',width:`${progress}%`,
        background:'linear-gradient(90deg,#00ff88,#00ccff)',boxShadow:'0 0 8px #00ff88',
        transition:'width 0.4s',zIndex:200}}/>

      {/* HEADER */}
      <div style={{borderBottom:'1px solid rgba(0,255,136,0.15)',padding:'14px 20px',
        display:'flex',alignItems:'center',justifyContent:'space-between',
        position:'relative',zIndex:10,background:'rgba(6,10,15,0.97)'}}>
        <div>
          <div style={{fontSize:'18px',fontWeight:700,color:'#00ff88',letterSpacing:'0.14em',
            textShadow:'0 0 18px rgba(0,255,136,0.45)'}}>
            ⬡ EDEN SNIPER — FUTURES SCANNER
          </div>
          <div style={{fontSize:'9px',color:'#2a4433',letterSpacing:'0.14em',marginTop:'3px'}}>
            BINANCE PERP · 7-SIGNAL ENGINE · 5M CHART · {lastScan?`LAST: ${lastScan.toLocaleTimeString()}`:'LOADING...'}
          </div>
        </div>
        <div style={{display:'flex',gap:'8px',alignItems:'center'}}>
          {autoScan&&<div style={{fontSize:'10px',color:'#2a4433',letterSpacing:'0.1em'}}>
            NEXT <span style={{color:'#00ff88'}}>{String(Math.floor(countdown/60)).padStart(2,'0')}:{String(countdown%60).padStart(2,'0')}</span>
          </div>}
          <button className="sbtn" onClick={()=>setAutoScan(v=>!v)} style={{
            background:autoScan?'rgba(0,255,136,0.08)':'transparent',
            border:`1px solid ${autoScan?'#00ff88':'#223333'}`,
            color:autoScan?'#00ff88':'#334455',padding:'7px 14px',fontSize:'10px',
            letterSpacing:'0.1em',cursor:'pointer',textTransform:'uppercase',
            fontFamily:"'JetBrains Mono',monospace",borderRadius:'2px',transition:'all 0.2s'}}>
            {autoScan?'● AUTO':'○ AUTO'}
          </button>
          <button className="sbtn" onClick={runScan} disabled={loading} style={{
            background:'transparent',border:'1px solid #00ff88',color:'#00ff88',
            padding:'7px 18px',fontSize:'10px',letterSpacing:'0.1em',cursor:'pointer',
            textTransform:'uppercase',fontFamily:"'JetBrains Mono',monospace",
            borderRadius:'2px',transition:'all 0.2s',opacity:loading?0.5:1}}>
            {loading?'◈ SCANNING...':'◈ SCAN NOW'}
          </button>
        </div>
      </div>

      {/* TABS */}
      <div style={{display:'flex',borderBottom:'1px solid rgba(0,255,136,0.08)',
        background:'rgba(6,10,15,0.97)',position:'sticky',top:0,zIndex:9}}>
        {[['all',`ALL (${coins.length})`],['hot',`🔥 HOT (${hotN})`],
          ['pump',`▲ PUMP (${pumpN})`],['dump',`▼ DUMP (${dumpN})`],
          ['watchlist',`★ WATCHLIST (${coins.filter(c=>c.isWatch).length})`]
        ].map(([id,lbl])=>(
          <button key={id} onClick={()=>setTab(id)} style={{
            padding:'9px 18px',fontSize:'10px',letterSpacing:'0.1em',textTransform:'uppercase',
            cursor:'pointer',border:'none',background:'transparent',
            color:tab===id?'#00ff88':'#334455',
            borderBottom:tab===id?'2px solid #00ff88':'2px solid transparent',
            fontFamily:"'JetBrains Mono',monospace",transition:'all 0.2s'}}>
            {lbl}
          </button>
        ))}
      </div>

      {/* BODY */}
      <div style={{padding:'16px 20px',position:'relative',zIndex:2}}>

        {/* Stats */}
        {coins.length>0&&(
          <div style={{display:'grid',gridTemplateColumns:'repeat(4,1fr)',gap:'10px',marginBottom:'16px'}}>
            {[
              ['Scanned',coins.length,'#00ff88'],
              ['🔥 Hot Signals',hotN,'#ffaa00'],
              ['▲ Pump Setups',pumpN,'#00ff88'],
              ['▼ Dump Setups',dumpN,'#ff4466'],
            ].map(([lbl,val,col])=>(
              <div key={lbl} style={{border:'1px solid rgba(0,255,136,0.1)',padding:'10px 14px',background:'rgba(0,255,136,0.02)'}}>
                <div style={{fontSize:'9px',color:'#2a4433',letterSpacing:'0.12em',textTransform:'uppercase'}}>{lbl}</div>
                <div style={{fontSize:'22px',fontWeight:700,color:col,marginTop:'4px'}}>{val}</div>
              </div>
            ))}
          </div>
        )}

        {/* Error */}
        {error&&<div style={{border:'1px solid rgba(255,68,102,0.3)',background:'rgba(255,68,102,0.07)',
          padding:'12px 18px',marginBottom:'14px',fontSize:'11px',color:'#ff8899',borderRadius:'2px'}}>
          ⚠ {error} — Make sure you're on a browser that allows cross-origin requests to fapi.binance.com
        </div>}

        {/* Loading spinner */}
        {loading&&coins.length===0&&(
          <div style={{display:'flex',flexDirection:'column',alignItems:'center',padding:'80px 0',gap:'14px'}}>
            <div style={{width:'44px',height:'44px',borderRadius:'50%',
              border:'2px solid rgba(0,255,136,0.1)',borderTop:'2px solid #00ff88',
              animation:'spin 1s linear infinite'}}/>
            <div style={{fontSize:'11px',color:'#2a4433',letterSpacing:'0.14em'}}>
              SCANNING BINANCE FUTURES... {Math.round(progress)}%
            </div>
          </div>
        )}

        {/* TABLE */}
        {filtered.length>0&&(
          <table style={{width:'100%',borderCollapse:'collapse'}}>
            <thead>
              <tr>
                {['COIN','SCORE','SIGNALS','DIR','PRICE','24H %','VOLUME','FUNDING RATE'].map(h=>(
                  <th key={h} style={{fontSize:'9px',color:'#2a4433',letterSpacing:'0.12em',
                    padding:'7px 10px',textAlign:'left',textTransform:'uppercase',
                    borderBottom:'1px solid rgba(0,255,136,0.08)'}}>{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {filtered.map(coin=>(
                <>
                  <tr key={coin.symbol} className="crow"
                    style={{borderBottom:'1px solid rgba(0,255,136,0.04)',
                      background:coin.score>=8?'rgba(255,68,102,0.04)':coin.score>=6?'rgba(255,170,0,0.03)':coin.score>=4?'rgba(0,255,136,0.02)':'transparent',
                      outline:coin.isWatch?'1px solid rgba(0,200,255,0.15)':'none'}}
                    onClick={()=>setExpanded(e=>e===coin.symbol?null:coin.symbol)}>

                    {/* Coin name */}
                    <td style={{padding:'10px 10px',verticalAlign:'middle'}}>
                      <div style={{display:'flex',alignItems:'center',gap:'7px'}}>
                        {coin.isWatch&&<span style={{color:'#00ccff',fontSize:'10px'}}>★</span>}
                        <div>
                          <div style={{fontWeight:700,fontSize:'13px',
                            color:coin.score>=6?'#ffffff':coin.score>=4?'#aabbcc':'#667788'}}>
                            {coin.base}
                          </div>
                          <div style={{fontSize:'8px',color:'#223333'}}>PERP</div>
                        </div>
                      </div>
                    </td>

                    {/* Score number */}
                    <td style={{padding:'10px 10px',verticalAlign:'middle'}}>
                      <div style={{display:'flex',flexDirection:'column',alignItems:'flex-start',gap:'5px'}}>
                        <span className={coin.score>=8?'hot-glow':''} style={{
                          fontSize:'20px',fontWeight:700,lineHeight:1,
                          color:coin.score>=8?'#ff4466':coin.score>=6?'#ffaa00':coin.score>=4?'#00ff88':'#334455'}}>
                          {coin.score}<span style={{fontSize:'10px',color:'#334455'}}>/{coin.maxScore}</span>
                        </span>
                        <div style={{width:'70px',height:'3px',background:'rgba(255,255,255,0.05)',borderRadius:'2px'}}>
                          <div style={{height:'100%',borderRadius:'2px',
                            width:`${(coin.score/coin.maxScore)*100}%`,
                            background:coin.score>=8?'linear-gradient(90deg,#ff4466,#ff6688)':
                                       coin.score>=6?'linear-gradient(90deg,#ffaa00,#ffcc44)':
                                       coin.score>=4?'linear-gradient(90deg,#00ff88,#00cccc)':
                                       '#223344',transition:'width 0.5s'}}/>
                        </div>
                      </div>
                    </td>

                    {/* Signal pills */}
                    <td style={{padding:'10px 10px',verticalAlign:'middle',maxWidth:'240px'}}>
                      <div style={{display:'flex',flexWrap:'wrap',gap:'3px'}}>
                        {coin.signals.slice(0,4).map(s=>(
                          <span key={s.id} style={{
                            padding:'2px 6px',fontSize:'8px',letterSpacing:'0.06em',
                            background:clsBg[s.cls]||clsBg.neutral,
                            color:clsColor[s.cls]||clsColor.neutral,
                            border:`1px solid ${(clsColor[s.cls]||clsColor.neutral)}33`,
                            borderRadius:'2px'}}>
                            {s.label}
                          </span>
                        ))}
                        {coin.signals.length>4&&<span style={{padding:'2px 6px',fontSize:'8px',color:'#334455',
                          background:'rgba(255,255,255,0.03)',border:'1px solid #223333',borderRadius:'2px'}}>
                          +{coin.signals.length-4}
                        </span>}
                      </div>
                    </td>

                    {/* Direction */}
                    <td style={{padding:'10px 10px',verticalAlign:'middle'}}>
                      {coin.score>=4?(
                        <span style={{
                          padding:'4px 10px',fontSize:'10px',letterSpacing:'0.08em',fontWeight:700,
                          borderRadius:'2px',display:'inline-block',
                          background:coin.direction==='PUMP'?'rgba(0,255,136,0.12)':coin.direction==='DUMP'?'rgba(255,68,102,0.12)':'rgba(0,200,255,0.08)',
                          color:coin.direction==='PUMP'?'#00ff88':coin.direction==='DUMP'?'#ff4466':'#00ccff',
                          border:`1px solid ${coin.direction==='PUMP'?'rgba(0,255,136,0.35)':coin.direction==='DUMP'?'rgba(255,68,102,0.35)':'rgba(0,200,255,0.2)'}`,
                          textShadow:coin.direction==='PUMP'?'0 0 8px rgba(0,255,136,0.4)':coin.direction==='DUMP'?'0 0 8px rgba(255,68,102,0.4)':'none'}}>
                          {coin.direction==='PUMP'?'▲ PUMP':coin.direction==='DUMP'?'▼ DUMP':'◈ COIL'}
                        </span>
                      ):<span style={{color:'#223333',fontSize:'9px'}}>—</span>}
                    </td>

                    {/* Price */}
                    <td style={{padding:'10px 10px',verticalAlign:'middle',color:'#99aabb',fontSize:'12px',fontWeight:500}}>
                      ${fmtP(coin.price)}
                    </td>

                    {/* 24h % */}
                    <td style={{padding:'10px 10px',verticalAlign:'middle',fontWeight:600,fontSize:'12px',
                      color:coin.change24h>=0?'#00cc77':'#ff4466'}}>
                      {coin.change24h>=0?'+':''}{coin.change24h.toFixed(2)}%
                    </td>

                    {/* Volume */}
                    <td style={{padding:'10px 10px',verticalAlign:'middle',color:'#445566',fontSize:'11px'}}>
                      ${fmtVol(coin.volume)}
                    </td>

                    {/* Funding */}
                    <td style={{padding:'10px 10px',verticalAlign:'middle',fontSize:'11px',
                      color:coin.fundingRate<-0.05?'#00ff88':coin.fundingRate>0.05?'#ff4466':'#445566'}}>
                      {coin.fundingRate>=0?'+':''}{coin.fundingRate.toFixed(4)}%
                    </td>
                  </tr>

                  {/* Expanded detail */}
                  {expanded===coin.symbol&&(
                    <tr key={`${coin.symbol}-x`}>
                      <td colSpan={8} style={{background:'rgba(0,0,0,0.3)',borderBottom:'1px solid rgba(0,255,136,0.1)'}}>
                        <div style={{padding:'14px 20px'}}>
                          <div style={{fontSize:'9px',color:'#2a4433',letterSpacing:'0.12em',marginBottom:'10px'}}>
                            ─ FULL SIGNAL BREAKDOWN: {coin.base}/USDT PERP — SCORE {coin.score}/{coin.maxScore} — {coin.direction} ─
                          </div>
                          {coin.signals.length>0?(
                            <div style={{display:'flex',flexWrap:'wrap',gap:'8px'}}>
                              {coin.signals.map(s=>(
                                <div key={s.id} style={{
                                  padding:'8px 14px',minWidth:'155px',
                                  background:clsBg[s.cls]||clsBg.neutral,
                                  border:`1px solid ${(clsColor[s.cls]||clsColor.neutral)}33`,
                                  borderLeft:`3px solid ${clsColor[s.cls]||clsColor.neutral}`,
                                }}>
                                  <div style={{fontSize:'10px',fontWeight:700,color:clsColor[s.cls]||clsColor.neutral}}>{s.label}</div>
                                  <div style={{fontSize:'9px',color:'#556677',marginTop:'3px'}}>{s.detail}</div>
                                  <div style={{fontSize:'8px',color:'#334455',marginTop:'2px'}}>+{s.weight} pts</div>
                                </div>
                              ))}
                            </div>
                          ):<div style={{fontSize:'11px',color:'#334455'}}>No signals fired.</div>}
                          <div style={{marginTop:'12px',display:'flex',flexWrap:'wrap',gap:'20px',fontSize:'9px',color:'#334455'}}>
                            <span>MARK ${fmtP(coin.markPrice)}</span>
                            <span>LAST ${fmtP(coin.price)}</span>
                            <span>SPREAD {((coin.markPrice-coin.price)/coin.price*100).toFixed(4)}%</span>
                            <span>FUNDING {coin.fundingRate>=0?'+':''}{coin.fundingRate.toFixed(5)}%</span>
                            <a href={`https://www.binance.com/en/futures/${coin.symbol}`}
                              target="_blank" rel="noreferrer"
                              onClick={e=>e.stopPropagation()}
                              style={{color:'#00ccff',textDecoration:'none'}}>
                              → Open Binance Chart ↗
                            </a>
                          </div>
                        </div>
                      </td>
                    </tr>
                  )}
                </>
              ))}
            </tbody>
          </table>
        )}

        {!loading&&filtered.length===0&&coins.length>0&&(
          <div style={{textAlign:'center',padding:'60px',color:'#223333',fontSize:'11px',letterSpacing:'0.12em'}}>
            NO SIGNALS MATCH THIS FILTER
          </div>
        )}

        {/* Legend */}
        {coins.length>0&&(
          <div style={{marginTop:'28px',padding:'14px 18px',
            border:'1px solid rgba(0,255,136,0.07)',background:'rgba(0,255,136,0.01)',
            display:'grid',gridTemplateColumns:'repeat(4,1fr)',gap:'10px',
            fontSize:'9px',color:'#334455',letterSpacing:'0.08em'}}>
            <div><span style={{color:'#334455'}}>SCORE 0–3</span> — Low noise</div>
            <div><span style={{color:'#00ff88'}}>SCORE 4–5</span> — Watch / forming</div>
            <div><span style={{color:'#ffaa00'}}>SCORE 6–7</span> — High alert</div>
            <div><span style={{color:'#ff4466'}}>SCORE 8+</span> — CRITICAL</div>
            <div><span style={{color:'#00ff88'}}>NEG FUNDING</span> → Shorts overloaded → squeeze</div>
            <div><span style={{color:'#ff4466'}}>POS FUNDING</span> → Longs overloaded → flush</div>
            <div><span style={{color:'#00ccff'}}>BB SQUEEZE</span> → Coil → explosion near</div>
            <div><span style={{color:'#ff44ff'}}>VOL SPIKE</span> → Breakout in progress</div>
          </div>
        )}
      </div>
    </div>
  );
}





