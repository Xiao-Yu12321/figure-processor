// Standalone browser processing. No server, network, or external libraries.
async function processLocalImage(form) {
  await new Promise(resolve => setTimeout(resolve, 30));
  const file = form.get('image');
  const scale = Number(form.get('scale'));
  const tolerance = Number(form.get('tolerance'));
  const padding = Number(form.get('padding'));
  const mode = form.get('background');
  const bitmap = await createImageBitmap(file, {imageOrientation: 'from-image'});
  const w = bitmap.width, h = bitmap.height, n = w * h;
  if (n > 6000000 || n * scale * scale > 24000000) {
    bitmap.close();
    throw new Error('本地版原图最多 600 万像素，放大后最多 2400 万像素，请缩小图片或降低倍数。');
  }
  const canvas = document.createElement('canvas');
  canvas.width = w; canvas.height = h;
  const context = canvas.getContext('2d', {willReadFrequently: true});
  context.drawImage(bitmap, 0, 0); bitmap.close();
  const image = context.getImageData(0, 0, w, h), pixels = image.data;
  let background = null;
  if (mode !== 'keep') {
    const border = [[], [], []];
    let total = 0;
    function sample(x, y) {
      total++;
      const i = (y * w + x) * 4;
      if (pixels[i + 3] > 242) for (let c = 0; c < 3; c++) border[c].push(pixels[i + c]);
    }
    for (let x = 0; x < w; x++) { sample(x, 0); sample(x, h - 1); }
    for (let y = 0; y < h; y++) { sample(0, y); sample(w - 1, y); }
    if (border[0].length > total / 2) {
      background = border.map(values => {values.sort((a,b) => a-b); return values[Math.floor(values.length / 2)];});
      const candidate = new Uint8Array(n), removed = new Uint8Array(n);
      for (let p = 0; p < n; p++) {
        const i = p * 4;
        const d = Math.max(...background.map((v, c) => Math.abs(pixels[i+c] - v)));
        candidate[p] = d <= tolerance || pixels[i+3] === 0 ? 1 : 0;
      }
      if (mode === 'uniform') removed.set(candidate);
      else {
        const queue = new Int32Array(n);
        let head = 0, tail = 0;
        function add(p) { if (candidate[p] && !removed[p]) {removed[p] = 1; queue[tail++] = p;} }
        for (let x = 0; x < w; x++) {add(x); add((h-1)*w+x);}
        for (let y = 0; y < h; y++) {add(y*w); add(y*w+w-1);}
        while (head < tail) {
          const p = queue[head++], x = p % w;
          if (x) add(p-1); if (x<w-1) add(p+1);
          if (p>=w) add(p-w); if (p<n-w) add(p+w);
        }
      }
      const lightPaper = Math.min(...background) >= 230;
      for (let p = 0; p < n; p++) {
        const i = p*4, x = p % w;
        if (removed[p]) {pixels[i+3]=0; continue;}
        const rim = (x && removed[p-1]) || (x<w-1 && removed[p+1]) || (p>=w && removed[p-w]) || (p<n-w && removed[p+w]);
        if ((lightPaper && mode === 'uniform') || rim) {
          let coverage;
          if (lightPaper) coverage = Math.max(0, Math.min(1, 1-Math.min(...background.map((v,c)=>pixels[i+c]/v))));
          else coverage = Math.max(0, Math.min(1, (Math.max(...background.map((v,c)=>Math.abs(pixels[i+c]-v)))-tolerance)/12));
          if (coverage>0 && coverage<1) for (let c=0; c<3; c++) pixels[i+c] = Math.max(0,Math.min(255,(pixels[i+c]-background[c]*(1-coverage))/coverage));
          pixels[i+3] = Math.round(pixels[i+3]*coverage);
        }
      }
    }
  }
  if (form.get('denoise') === 'true') {
    const source = pixels.slice();
    for (let y=1; y<h-1; y++) for (let x=1; x<w-1; x++) {
      const i=(y*w+x)*4;
      if (!source[i+3]) continue;
      // Filter only opaque interiors, so transparent boundaries stay crisp.
      let opaque = true;
      for (let dy=-1;dy<=1;dy++) for(let dx=-1;dx<=1;dx++) if(source[((y+dy)*w+x+dx)*4+3] !== 255) opaque=false;
      if (!opaque) continue;
      for(let c=0;c<3;c++) {
        const values=[];
        for(let dy=-1;dy<=1;dy++) for(let dx=-1;dx<=1;dx++) values.push(source[((y+dy)*w+x+dx)*4+c]);
        values.sort((a,b)=>a-b); pixels[i+c]=values[4];
      }
    }
  }
  let left=w, top=h, right=-1, bottom=-1;
  for(let y=0;y<h;y++) for(let x=0;x<w;x++) if(pixels[(y*w+x)*4+3]) {
    left=Math.min(left,x);right=Math.max(right,x);top=Math.min(top,y);bottom=Math.max(bottom,y);
  }
  if (right<left) throw new Error('没有找到可保留的内容，请降低容差或选择保留背景。');
  context.putImageData(image,0,0);
  const output=document.createElement('canvas');
  const width=(right-left+1)*scale, height=(bottom-top+1)*scale;
  output.width=width+2*padding; output.height=height+2*padding;
  const out=output.getContext('2d',{willReadFrequently:true});
  out.imageSmoothingEnabled=true;out.imageSmoothingQuality='high';
  out.drawImage(canvas,left,top,right-left+1,bottom-top+1,padding,padding,width,height);
  const sharpen=Number(form.get('sharpen'))/100;
  if(sharpen>0) {
    const img=out.getImageData(0,0,output.width,output.height), source=img.data.slice(), target=img.data, ow=output.width;
    for(let y=1;y<output.height-1;y++) for(let x=1;x<ow-1;x++) {
      const i=(y*ow+x)*4;
      if(!source[i+3]) continue;
      // Alpha-weighted local blur avoids sharpening invisible background colors.
      for(let c=0;c<3;c++) {
        let sum=0, weight=0;
        for(const offset of [-ow,-1,0,1,ow]) {const j=i+offset*4;sum+=source[j+c]*source[j+3];weight+=source[j+3];}
        const blurred=weight?sum/weight:source[i+c];
        target[i+c]=Math.max(0,Math.min(255,source[i+c]+sharpen*(source[i+c]-blurred)));
      }
    }
    out.putImageData(img,0,0);
  }
  return {image:output.toDataURL('image/png'), original:[w,h],output:[output.width,output.height],background};
}
