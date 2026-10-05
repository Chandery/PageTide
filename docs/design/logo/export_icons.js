// Exports the final PaperDig app icon (bookmark sea lion) from sealion.html as standalone SVGs.
// Usage: node docs/design/logo/export_icons.js   (run from anywhere)
const fs=require("fs"), vm=require("vm"), path=require("path");
const here=__dirname, root=path.resolve(here,"../../.."), OUT=path.join(here,"final");
const h=fs.readFileSync(path.join(here,"sealion.html"),"utf8"), js=h.split("<script>")[1].split("</script>")[0];
const stub=()=>({innerHTML:""}), ctx={document:{body:stub()},big:stub(),mid:stub(),small:stub(),lk:stub()};
vm.createContext(ctx); vm.runInContext(js+";this.__={seal,INK,PAPER,G};",ctx);
const {seal,INK,PAPER,G}=ctx.__;
const svg=(o,crop=false)=>{let v=seal({tailOn:false,id:"i",...o}).replace(/ width="SIZE" height="SIZE"/,' xmlns="http://www.w3.org/2000/svg"');
  // crop to the squircle for in-app / favicon use (no macOS grid margin)
  if(crop) v=v.replace('viewBox="0 0 1024 1024"','viewBox="100 100 824 824"');
  return v.replace(/\n\s*/g,"")+"\n";};
// Small sizes (<=32 px): drop blush, widen the flipper gap and enlarge the eye so they survive downsampling.
const SMALL={blush:false, gap:30, eyeR:26};
// Tiny 1x slots (16 / 32 px, shown on non-Retina displays): the generic SMALL master loses its
// 1.4 px bookmark (it blends to pink) and wastes 20% on the macOS grid margin. Tuned masters:
// tighter margin (viewBox), bigger seal, solid wider bookmark, larger eye / flipper gap.
const tuned=({vb,K,ty,eyeR,gap,bm})=>{
  const k0=G.K; G.K=K;
  let v=svg({blush:false,gap,eyeR});
  G.K=k0;
  v=v.replace('viewBox="0 0 1024 1024"',`viewBox="${vb} ${vb} ${1024-2*vb} ${1024-2*vb}"`)
     .replace("translate(512 528)",`translate(512 ${ty})`)
     .replace("M702 -40H786V196L744 164L702 196Z",bm);
  return v;};
const TINY16=tuned({vb:72,K:1.1,ty:560,eyeR:36,gap:40,bm:"M676 -40H812V210L744 170L676 210Z"});
const TINY32=tuned({vb:72,K:1.05,ty:545,eyeR:34,gap:30,bm:"M684 -40H806V205L745 168L684 205Z"});
const files={
  "paperdig-icon-16.svg":TINY16,
  "paperdig-icon-32.svg":TINY32,
  "paperdig-icon.svg":svg({}),
  "paperdig-icon-small.svg":svg(SMALL),
  "paperdig-icon-dark.svg":svg({bg:INK,body_c:PAPER}),
  "paperdig-icon-mono.svg":svg({mono:true,bg:"#FFFFFF"}),
};
fs.mkdirSync(OUT,{recursive:true});
for(const [n,v] of Object.entries(files)) fs.writeFileSync(path.join(OUT,n),v);
fs.writeFileSync(path.join(root,"app/static/brand-mark.svg"),svg(SMALL,true));
fs.writeFileSync(path.join(root,"app/static/favicon.svg"),svg(SMALL,true));
console.log(Object.keys(files).join(" "),"+ app/static/{brand-mark,favicon}.svg");
