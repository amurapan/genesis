const routes=['workspace','architecture','guide'];
// Preserve links shared before the landing page existed. #verification now names the landing section.
if(routes.includes(location.hash.slice(1))||new URLSearchParams(location.search).has('episode')){
 const target=new URL('lab.html',location.href);target.hash=location.hash;target.search=location.search;location.replace(target);
}
const root=document.documentElement,hero=document.querySelector('.hero'),visual=document.querySelector('.hero-visual'),rig=document.querySelector('#scene-rig');
const motionQuery=matchMedia('(prefers-reduced-motion: reduce)'),compactQuery=matchMedia('(max-width: 650px)');
let stored=false;try{stored=localStorage.getItem('sled-motion')==='off';}catch{}
let motionOff=motionQuery.matches||stored,heroVisible=true,frame=0,targetX=0,targetZ=0,currentX=0,currentZ=0,scrollY=0;
const toggle=document.querySelector('#motion-toggle'),story=document.querySelector('#investigation'),display=document.querySelector('#story-display');
let stage=0,manualScroll=NaN;
const texts=[
 '30 ноября компания получает 100 USD. Опубликованный курс — 450 KZT за доллар. В книге должно появиться 45 000 KZT.',
 'В книге — 44 000 KZT и дата 1 декабря. Агент обнаруживает два расхождения: валютный курс и отнесение операции к отчётному периоду.',
 'Каждый вывод связан с первичными записями. Оценщик проверяет тип, сумму, валюту и полный набор доказательств. Красивого объяснения недостаточно.'
],states=['Первичные документы','Два расхождения','Доказательства собраны'];
function setStage(next){if(next===stage&&display.dataset.stage===String(next))return;stage=next;display.dataset.stage=String(stage);display.setAttribute('aria-labelledby','story-tab-'+stage);document.querySelector('#story-description').textContent=texts[stage];document.querySelector('#story-state').textContent=states[stage];document.querySelectorAll('[data-story]').forEach(el=>{const active=Number(el.dataset.story)===stage;el.setAttribute('aria-selected',String(active));el.tabIndex=active?0:-1;});}
function updateMotion(){root.classList.toggle('motion-off',motionOff);toggle.setAttribute('aria-pressed',String(motionOff));toggle.setAttribute('aria-label',motionOff?'Включить анимацию':'Отключить анимацию');toggle.querySelector('path').setAttribute('d',motionOff?'m8 5 10 7-10 7V5Z':'M9 5v14M15 5v14');if(motionOff){cancelAnimationFrame(frame);frame=0;}else requestFrame();}
toggle.addEventListener('click',()=>{motionOff=!motionOff;stored=motionOff;try{localStorage.setItem('sled-motion',motionOff?'off':'on');}catch{}updateMotion();});
motionQuery.addEventListener('change',e=>{motionOff=e.matches||stored;updateMotion();});
function animate(){frame=0;if(motionOff||document.hidden)return;currentX+=(targetX-currentX)*.065;currentZ+=(targetZ-currentZ)*.065;if(heroVisible){rig.style.setProperty('--cam-x',currentX.toFixed(3)+'deg');rig.style.setProperty('--cam-z',(currentZ+scrollY*8).toFixed(3)+'deg');rig.style.setProperty('--cam-y',(-scrollY*55).toFixed(2)+'px');}if(Math.abs(targetX-currentX)>.02||Math.abs(targetZ-currentZ)>.02)requestFrame();}
function requestFrame(){if(!frame&&!motionOff&&!document.hidden)frame=requestAnimationFrame(animate);}
visual.addEventListener('pointermove',e=>{if(e.pointerType==='touch'||motionOff)return;const r=visual.getBoundingClientRect();targetX=-(e.clientY-r.top-r.height/2)/r.height*6;targetZ=(e.clientX-r.left-r.width/2)/r.width*6;requestFrame();});
visual.addEventListener('pointerleave',()=>{targetX=targetZ=0;requestFrame();});
function onScroll(){scrollY=Math.max(0,Math.min(1,window.scrollY/hero.offsetHeight));requestFrame();if(!compactQuery.matches&&!motionOff){const r=story.getBoundingClientRect();if(r.top<innerHeight*.25&&r.bottom>innerHeight*.5){const progress=Math.max(0,Math.min(.999,-r.top/Math.max(1,story.offsetHeight-innerHeight)));if(!Number.isFinite(manualScroll)||Math.abs(window.scrollY-manualScroll)>100){setStage(Math.min(2,Math.floor(progress*3)));manualScroll=NaN;}}}}
window.addEventListener('scroll',onScroll,{passive:true});window.addEventListener('resize',onScroll,{passive:true});
document.querySelectorAll('[data-story]').forEach(el=>{el.addEventListener('click',()=>{manualScroll=window.scrollY;setStage(Number(el.dataset.story));});el.addEventListener('keydown',e=>{const keys=['ArrowLeft','ArrowRight','Home','End'];if(!keys.includes(e.key))return;e.preventDefault();let next=e.key==='Home'?0:e.key==='End'?2:(stage+(e.key==='ArrowRight'?1:2))%3;manualScroll=window.scrollY;setStage(next);document.querySelector('[data-story="'+next+'"]').focus();});});
document.addEventListener('visibilitychange',()=>{hero.classList.toggle('scene-paused',document.hidden||!heroVisible);if(document.hidden){cancelAnimationFrame(frame);frame=0;}else requestFrame();});
if('IntersectionObserver'in window){new IntersectionObserver(entries=>{heroVisible=entries[0].isIntersecting;hero.classList.toggle('scene-paused',!heroVisible);if(heroVisible)requestFrame();}).observe(hero);const observer=new IntersectionObserver(entries=>{for(const e of entries)if(e.isIntersecting){e.target.classList.add('revealed');if(!motionOff)e.target.animate([{opacity:0,transform:'translateY(24px)'},{opacity:1,transform:'translateY(0)'}],{duration:700,easing:'cubic-bezier(.2,.7,.2,1)'});observer.unobserve(e.target);}},{threshold:.08});root.classList.add('reveal-ready');document.querySelectorAll('[data-reveal]').forEach(el=>observer.observe(el));}
updateMotion();onScroll();
