"use strict";
const releasePage = "https://github.com/Interprole/NanoCut/releases/latest";
function timingMates(c) {
  return ed.p.clips.filter(k => k === c || (c.link && k.link === c.link &&
    k.start === c.start && k.length === c.length && k.asset === c.asset && k.offset === c.offset && k.rate === c.rate));
}
function styleGallery(container, current, choose) {
  const gallery=node("div","style-gallery");
  for(const name of styles) {
    const b=button("",name,()=>{
      for(const option of gallery.children) option.setAttribute("aria-pressed",option===b);
      choose(name);
    });
    b.append(node("span","cue "+name,"The quick cut"),node("small","",name));
    b.setAttribute("aria-pressed",name===current);
    gallery.append(b);
  }
  container.append(gallery);
}
function clipRegion(c) {
  if (!ed.range || ed.range.lane !== c.track) return {start:c.start,length:c.length};
  const start=Math.max(c.start,ed.range.a), end=Math.min(c.start+c.length,ed.range.b);
  if(end<=start) throw Error("The marked range does not overlap this clip.");
  return {start,length:end-start};
}
function captionLayer(c,cues,style,region={start:c.start,length:c.length}) {
  const layer={...copy(c),...region,id:uid(),kind:"caption",track:newTrack(true,c.track>0?c.track:undefined),
    offset:c.offset+(region.start-c.start)*c.rate/ed.p.fps,style,cues,volume:0,guide:false};
  delete layer.link;
  layer.hideCaptions=false;
  ed.p.clips.push(layer); selectClip(layer); return layer;
}
async function checkUpdates(manual) {
  try {
    const r=await api("update");
    if(r.newer) {
      const b=$("release-link");
      b.hidden=false; b.textContent="Update to "+r.version;
      if(manual) status("A new installer is available on GitHub.");
    } else if(manual) status("NanoCut 1.1.0.1 is up to date.");
  } catch(e) { if(manual) status("GitHub could not be reached. Open File → GitHub releases to check manually."); }
}
function toolDialog() {
  showForm("Models and tools",[{key:"component",label:"Component",options:[
    ...Object.keys(settings.models).map(s=>[s,"Whisper "+s]),["foreground","Background removal"],
    ["downloader","Update yt-dlp"]]}], async v=>{
    const result=await task("install",v,"Prepare "+v.component);
    if(result) status(v.component+" is ready");
  },"Prepare","Existing model files are reused. Large Whisper models can take several gigabytes.");
}
function linkPreview(input,help) {
  const preview=node("iframe","link-preview");
  preview.title="Video preview"; preview.hidden=true;
  preview.allow="fullscreen; encrypted-media; picture-in-picture"; preview.referrerPolicy="strict-origin-when-cross-origin";
  help.before(preview);
  input.oninput=()=>{
    let src="";
    try {
      const u=new URL(input.value.trim()), h=u.hostname.replace(/^(www\.|m\.)/,""), parts=u.pathname.split("/");
      if(u.protocol==="https:" && ["youtube.com","youtu.be"].includes(h)){
        const id=h==="youtu.be"?parts[1]:u.searchParams.get("v") || (["shorts","embed","live"].includes(parts[1])?parts[2]:"");
        if(/^[\w-]{11}$/.test(id)) src="https://www.youtube-nocookie.com/embed/"+id;
      } else if(u.protocol==="https:" && h==="tiktok.com"){
        const id=u.pathname.match(/\/video\/(\d+)/)?.[1];
        if(id) src="https://www.tiktok.com/player/v1/"+id;
      }
    } catch {}
    preview.hidden=!src;
    if(src && preview.getAttribute("src")!==src) preview.src=src;
    if(!src) preview.removeAttribute("src");
    help.textContent=src?"Play the preview above. Downloaded media is saved with the project.":"Paste the full video link for a preview. Short TikTok share links can also be downloaded.";
  };
  $("modal").addEventListener("close",()=>preview.removeAttribute("src"),{once:true});
}
function clippedCues(c,region) {
  const fps=ed.p.fps, offset=c.offset+(region.start-c.start)*c.rate/fps, duration=region.length/fps;
  const cues=c.cues.map(q=>({in:Math.max(0,(q.in-offset)/c.rate),out:Math.min(duration,(q.out-offset)/c.rate),text:q.text})).filter(q=>q.out>q.in);
  if(!cues.length) throw Error("This interval has no captions.");
  return cues;
}
function languageFields() {
  return [{key:"source",label:"Source language code",value:"en",required:true},
    {key:"target",label:"Target language code",value:"ru",required:true}];
}
const providerOptions=[["local","Local on this computer"],["openai","OpenAI API"]];
function translateDialog(c) {
  const region=clipRegion(c),cues=clippedCues(c,region);
  const {controls}=showForm("Translate subtitles",[
    {key:"provider",label:"Translator",options:providerOptions},...languageFields(),
    {key:"model",label:"API translation model",value:"gpt-4o-mini"},
    {key:"key",type:"password",label:"OpenAI key · this task only"}],async v=>{
      const result=await task("translate",{...v,cues},"Translate subtitles");
      if(!result) return;
      checkpoint();
      const layer=captionLayer(c,result,c.style,region); layer.offset=0;layer.rate=1;
      if(c.kind==="caption" && region.length===c.length) c.hideCaptions=true;
      changed("Translated caption layer created");
    },"Translate","Local mode downloads the selected Argos language pair once. API mode sends caption text to OpenAI.");
  function update(){for(const key of ["model","key"]) controls[key].parentElement.hidden=controls.provider.value!=="openai";}
  controls.provider.onchange=update;update();
}
function voiceDialog(c) {
  const region=clipRegion(c),cues=clippedCues(c,region);
  const {controls}=showForm("Voice captions",[
    {key:"translate",label:"Script",options:[["no","Read these captions"],["local","Translate first · local Argos"],["openai","Translate first · OpenAI"]]},
    ...languageFields(),{key:"provider",label:"Voice engine",options:[["piper","Piper · local neural voice"],["local","System desktop voice"],["openai","OpenAI API"]]},
    {key:"piperVoice",label:"Piper voice",options:[["en_US-lessac-medium","English · Lessac"],["ru_RU-irina-medium","Russian · Irina"],["de_DE-thorsten-medium","German · Thorsten"],["fr_FR-siwis-medium","French · Siwis"],["es_ES-davefx-medium","Spanish · Dave"]]},
    {key:"voice",label:"Voice name",placeholder:"Blank uses the default voice"},
    {key:"model",label:"API speech model",value:"gpt-4o-mini-tts"},
    {key:"key",type:"password",label:"OpenAI key · this task only"}],async v=>{
      let spoken=cues;
      if(v.translate!=="no") {
        spoken=await task("translate",{...v,model:"gpt-4o-mini",provider:v.translate,cues},"Translate dialogue");
        if(!spoken) return;
      }
      const result=await task("narrate",{...v,cues:spoken,duration:region.length/ed.p.fps},"Voice captions");
      if(!result) return;
      checkpoint();register(result);
      if(v.translate!=="no") {const layer=captionLayer(c,spoken,c.style,region);layer.offset=0;layer.rate=1;}
      const voice=addClip(result[0].id,newTrack(false),region.start);
      voice.length=region.length;
      changed("Narration added on a new audio track");
    },"Create voice track","Speech is fitted to each caption. Piper downloads the selected neural voice once. Choose a voice for the target language. API mode sends caption text to OpenAI.");
  function update(){
    controls.piperVoice.parentElement.hidden=controls.provider.value!=="piper";
    controls.voice.parentElement.hidden=controls.provider.value==="piper";
    controls.model.parentElement.hidden=controls.provider.value!=="openai";
    controls.key.parentElement.hidden=controls.provider.value!=="openai"&&controls.translate.value!=="openai";
    for(const key of ["source","target"]) controls[key].parentElement.hidden=controls.translate.value==="no";
  }
  controls.provider.onchange=controls.translate.onchange=update;update();
}
let graph;
const audioNodes = new WeakMap();
function applyAudioFx(el,c) {
  if(!c.audioFx && !audioNodes.has(el)) return;
  if(!graph) graph=new AudioContext();
  if(ed.playing && graph.state==="suspended") graph.resume().catch(()=>{});
  let nodes=audioNodes.get(el);
  if(!nodes) {
    const src=graph.createMediaElementSource(el), filter=graph.createBiquadFilter();
    src.connect(filter).connect(graph.destination);
    nodes={src,filter};audioNodes.set(el,nodes);
  }
  nodes.filter.type=({voice:"highpass",soft:"lowpass"})[c.audioFx] || "allpass";
  nodes.filter.frequency.value=c.audioFx==="soft"?2400:160;
  nodes.filter.Q.value=.707;
}
function disconnectFx(el){
  const nodes=audioNodes.get(el);
  if(nodes){nodes.src.disconnect();nodes.filter.disconnect();audioNodes.delete(el);}
}
function graphicDialog(){
  showForm("Add graphic",[{key:"kind",label:"Graphic",options:["Text","Rectangle","Ellipse"]},
    {key:"text",label:"Text",value:"Title",maxLength:500},{key:"color",type:"color",label:"Color",value:"#ffffff"}],async v=>{
    const cv=document.createElement("canvas");cv.width=1200;cv.height=600;
    const ctx=cv.getContext("2d");ctx.fillStyle=v.color;
    if(v.kind==="Text"){ctx.font="bold 140px Arial";ctx.textAlign="center";ctx.textBaseline="middle";ctx.fillText(v.text,600,300,1160);}
    else if(v.kind==="Rectangle") ctx.fillRect(90,75,1020,450);
    else {ctx.beginPath();ctx.ellipse(600,300,510,225,0,0,2*Math.PI);ctx.fill();}
    const result=await task("graphic",{png:cv.toDataURL().split(",")[1]},"Create graphic");
    if(result){checkpoint();register(result);addClip(result[0].id,newTrack(true),ed.frame);changed("Graphic added");}
  },"Add to timeline");
}
function addDialog(){
  showForm("Add to timeline",[{key:"kind",label:"Item",options:["Video track","Audio track","Text or shape","Sound effect"]}],async v=>{
    if(v.kind==="Text or shape")return graphicDialog();
    if(v.kind==="Sound effect"){
      showForm("Add sound effect",[{key:"sound",label:"Sound",options:["Beep","Bass hit","Noise sweep"]}],async d=>{
        const r=await task("sound",d,"Create sound");
        if(r){checkpoint();register(r);addClip(r[0].id,newTrack(false),ed.frame);changed("Sound added");}
      },"Add sound");return;
    }
    checkpoint();newTrack(v.kind==="Video track");changed(v.kind+" added");
  },"Continue");
}
function isolateRange(){
  if(!ed.range) throw Error("Shift-drag a track to mark a time range.");
  const {a,b,lane}=ed.range;
  const hits=ed.p.clips.filter(c=>c.track===lane && c.start<b && a<c.start+c.length);
  if(!hits.length)throw Error("The marked interval is empty.");
  checkpoint();
  const groups=new Set(hits.map(c=>c.link).filter(Boolean)), ids=[],links=new Map();
  for(const c of [...ed.p.clips]){
    if(!hits.includes(c) && !groups.has(c.link)) continue;
    if(c.start>=b || c.start+c.length<=a) continue;
    const cuts=[c.start,...[a,b].filter(x=>c.start<x && x<c.start+c.length),c.start+c.length];
    const orig=copy(c);
    for(let i=0;i<cuts.length-1;i++){
      const start=cuts[i],part=i?{...copy(orig),id:uid()}:c;
      Object.assign(part,{start,length:cuts[i+1]-start,offset:orig.offset+(start-orig.start)*orig.rate/ed.p.fps});
      if(orig.link){
        const key=orig.link+"-"+(start<a?"left":start>=b?"right":"middle");
        if(!links.has(key)) links.set(key,uid());part.link=links.get(key);
      }
      if(i) ed.p.clips.push(part);
      if(start>=a && start<b && part.track===lane) ids.push(part.id);
    }
  }
  ed.multi=ids;ed.selected=ids[0];changed("Marked interval isolated");
}
function selectionDialog(){
  showForm("Selection",[{key:"action",label:"Action",options:["Isolate marked range","Link selected clips","Unlink selected clips","Clear range"]}],v=>{
    if(v.action==="Isolate marked range") return isolateRange();
    if(v.action==="Clear range"){ed.range=null;ed.loop=false;refresh();return;}
    const items=selectedClips();if(!items.length)throw Error("Select clips on the timeline first.");
    if(v.action.startsWith("Link") && items.length<2)throw Error("Ctrl-click at least two clips.");
    checkpoint();const group=uid();
    for(const c of items){if(v.action.startsWith("Unlink"))delete c.link;else c.link=group;}
    changed("Clip links updated");
  },"Apply","Ctrl-click clips or track labels to select several. Shift-drag a track to select a frame range.");
}
function arrangeLayer(c,action){
  if(action==="Duplicate on this track"){selectClip(c);duplicate();return;}
  checkpoint();
  if(action==="Reset transform"){Object.assign(c,{x:.5,y:.5,scale:1,rotation:0});}
  else{
    const rows=tracks(), order=rows.filter(t=>t>0);
    let index=order.indexOf(c.track);
    if(action==="Bring to front")index=order.length-1;
    if(action==="Send to back")index=0;
    const forward=action.startsWith("Bring");
    if(action==="Bring forward")index=Math.min(index+1,order.length-1);
    if(action==="Send backward")index=Math.max(index-1,0);
    const anchor=order[index], dest=newTrack(true,anchor);
    if(!forward){rows.splice(rows.indexOf(dest),1);rows.splice(rows.indexOf(anchor),0,dest);}
    c.track=dest;
  }
  changed("Layer updated");
}
function initStudio(){
  $("add-element").onclick=safe(addDialog);
  $("edit-selection").onclick=safe(selectionDialog);
  $("loop-range").onclick=()=>{
    if(!ed.range || ed.range.a>=endFrame()) return status("Shift-drag a track to mark a loop inside the timeline.");
    ed.loop=!ed.loop;$("loop-range").setAttribute("aria-pressed",ed.loop);
    if(ed.loop)seek(ed.range.a,true);
  };
  $("stage").oncontextmenu=e=>{
    const id=e.target.dataset.clip,c=ed.p.clips.find(c=>c.id===id);if(!c)return;
    e.preventDefault();selectClip(c);refresh();
    const menu=node("div","context-menu"); document.querySelector(".context-menu")?.remove();
    for(const action of ["Bring forward","Bring to front","Send backward","Send to back","Reset transform","Duplicate on this track"])
      menu.append(button(action,action,()=>{arrangeLayer(c,action);menu.remove();}));
    menu.style.left=Math.min(e.clientX,innerWidth-170)+"px";menu.style.top=Math.min(e.clientY,innerHeight-205)+"px";
    document.body.append(menu);
    document.addEventListener("pointerdown",function dismiss(ev){if(!menu.contains(ev.target))menu.remove();document.removeEventListener("pointerdown",dismiss);},true);
  };
  $("release-link").onclick=()=>window.open(releasePage,"_blank","noopener");
}
