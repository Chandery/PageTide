// Exports the final PaperDig app icon (bookmark sea lion) from sealion.html as standalone SVGs.
// Usage: node docs/design/logo/export_icons.js   (run from anywhere)
const fs=require("fs"), vm=require("vm"), path=require("path");
const here=__dirname, root=path.resolve(here,"../../.."), OUT=path.join(here,"final");
const h=fs.readFileSync(path.join(here,"sealion.html"),"utf8"), js=h.split("<script>")[1].split("</script>")[0];
const stub=()=>({innerHTML:""}), ctx={document:{body:stub()},big:stub(),mid:stub(),small:stub(),lk:stub()};
vm.createContext(ctx); vm.runInContext(js+";this.__={seal,INK,PAPER};",ctx);
const {seal,INK,PAPER}=ctx.__;
const svg=(o,crop=false)=>{let v=seal({tailOn:false,id:"i",...o}).replace(/ width="SIZE" height="SIZE"/,' xmlns="http://www.w3.org/2000/svg"');
  // crop to the squircle for in-app / favicon use (no macOS grid margin)
  if(crop) v=v.replace('viewBox="0 0 1024 1024"','viewBox="100 100 824 824"');
  return v.replace(/\n\s*/g,"")+"\n";};
// Small sizes (<=32 px): drop blush, widen the flipper gap and enlarge the eye so they survive downsampling.
const SMALL={blush:false, gap:30, eyeR:26};
const files={
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
