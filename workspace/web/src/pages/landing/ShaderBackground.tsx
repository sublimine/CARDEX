import { useEffect, useRef } from 'react'

/**
 * Liquid-mirror atmosphere — raw WebGL fragment shader.
 * Domain-warped fbm plasma in indigo/violet/teal over near-black, animated on
 * the GPU (zero main-thread cost). Fixed behind the page; the dark narrative
 * sections sit on it with low-opacity veils so the atmosphere flows through.
 * Falls back silently to a static CSS gradient if WebGL is unavailable.
 */

const FRAG = `
precision highp float;
uniform vec2  u_res;
uniform float u_time;
uniform vec2  u_mouse;

// hash / simplex noise (Ashima-style, trimmed)
vec3 mod289(vec3 x){return x-floor(x*(1.0/289.0))*289.0;}
vec2 mod289(vec2 x){return x-floor(x*(1.0/289.0))*289.0;}
vec3 permute(vec3 x){return mod289(((x*34.0)+1.0)*x);}
float snoise(vec2 v){
  const vec4 C=vec4(0.211324865405187,0.366025403784439,-0.577350269189626,0.024390243902439);
  vec2 i=floor(v+dot(v,C.yy));
  vec2 x0=v-i+dot(i,C.xx);
  vec2 i1=(x0.x>x0.y)?vec2(1.0,0.0):vec2(0.0,1.0);
  vec4 x12=x0.xyxy+C.xxzz; x12.xy-=i1;
  i=mod289(i);
  vec3 p=permute(permute(i.y+vec3(0.0,i1.y,1.0))+i.x+vec3(0.0,i1.x,1.0));
  vec3 m=max(0.5-vec3(dot(x0,x0),dot(x12.xy,x12.xy),dot(x12.zw,x12.zw)),0.0);
  m=m*m; m=m*m;
  vec3 x=2.0*fract(p*C.www)-1.0;
  vec3 h=abs(x)-0.5;
  vec3 ox=floor(x+0.5);
  vec3 a0=x-ox;
  m*=1.79284291400159-0.85373472095314*(a0*a0+h*h);
  vec3 g;
  g.x=a0.x*x0.x+h.x*x0.y;
  g.yz=a0.yz*x12.xz+h.yz*x12.yw;
  return 130.0*dot(m,g);
}
float fbm(vec2 p){
  float s=0.0, a=0.5;
  for(int i=0;i<5;i++){ s+=a*snoise(p); p*=2.02; a*=0.5; }
  return s;
}

void main(){
  vec2 uv=gl_FragCoord.xy/u_res.xy;
  vec2 p=(gl_FragCoord.xy-0.5*u_res.xy)/u_res.y;
  float t=u_time*0.04;

  // domain warp — flowing liquid feel
  vec2 q=vec2(fbm(p*1.3+vec2(0.0,t)), fbm(p*1.3+vec2(5.2,-t)));
  vec2 r=vec2(fbm(p*1.3+1.8*q+vec2(1.7,9.2)+0.15*t), fbm(p*1.3+1.8*q+vec2(8.3,2.8)-0.12*t));
  float f=fbm(p*1.3+2.4*r);

  // subtle mouse-reactive lift
  float md=1.0-smoothstep(0.0,0.7,length(p-u_mouse));

  vec3 base=vec3(0.024,0.024,0.055);
  vec3 indigo=vec3(0.20,0.18,0.55);
  vec3 violet=vec3(0.36,0.16,0.52);
  vec3 teal=vec3(0.10,0.32,0.40);

  vec3 col=base;
  col=mix(col, indigo, smoothstep(0.0,1.1,f)*0.55);
  col=mix(col, violet, smoothstep(0.2,1.0,r.x*r.y+0.5)*0.30);
  col=mix(col, teal,   smoothstep(0.55,1.0,q.y+0.5)*0.16);
  col+=indigo*md*0.10;

  // veins / specular threads
  float vein=smoothstep(0.78,0.82,fract(f*1.5+t));
  col+=vec3(0.34,0.30,0.55)*vein*0.06;

  // vignette + filmic falloff
  float vig=smoothstep(1.25,0.25,length(p));
  col*=0.35+0.65*vig;

  // grain
  float g=fract(sin(dot(gl_FragCoord.xy,vec2(12.9898,78.233))+u_time)*43758.5453);
  col+=(g-0.5)*0.015;

  gl_FragColor=vec4(col,1.0);
}
`

const VERT = `attribute vec2 a; void main(){ gl_Position=vec4(a,0.0,1.0); }`

function compile(gl: WebGLRenderingContext, type: number, src: string) {
  const s = gl.createShader(type)!
  gl.shaderSource(s, src); gl.compileShader(s)
  if (!gl.getShaderParameter(s, gl.COMPILE_STATUS)) { gl.deleteShader(s); return null }
  return s
}

export default function ShaderBackground() {
  const canvasRef = useRef<HTMLCanvasElement>(null)
  const mouse = useRef({ x: 0, y: 0, tx: 0, ty: 0 })

  useEffect(() => {
    const canvas = canvasRef.current
    if (!canvas) return
    const reduced = window.matchMedia('(prefers-reduced-motion: reduce)').matches
    const gl = canvas.getContext('webgl', { antialias: false, alpha: false, powerPreference: 'low-power' })
    if (!gl) { canvas.style.background = 'radial-gradient(120% 80% at 70% 10%, #14132e 0%, #06060e 60%)'; return }

    const vs = compile(gl, gl.VERTEX_SHADER, VERT)
    const fs = compile(gl, gl.FRAGMENT_SHADER, FRAG)
    if (!vs || !fs) { canvas.style.background = 'radial-gradient(120% 80% at 70% 10%, #14132e 0%, #06060e 60%)'; return }
    const prog = gl.createProgram()!
    gl.attachShader(prog, vs); gl.attachShader(prog, fs); gl.linkProgram(prog)
    if (!gl.getProgramParameter(prog, gl.LINK_STATUS)) { canvas.style.background = 'radial-gradient(120% 80% at 70% 10%, #14132e 0%, #06060e 60%)'; return }
    gl.useProgram(prog)

    const buf = gl.createBuffer()
    gl.bindBuffer(gl.ARRAY_BUFFER, buf)
    gl.bufferData(gl.ARRAY_BUFFER, new Float32Array([-1, -1, 3, -1, -1, 3]), gl.STATIC_DRAW)
    const aLoc = gl.getAttribLocation(prog, 'a')
    gl.enableVertexAttribArray(aLoc)
    gl.vertexAttribPointer(aLoc, 2, gl.FLOAT, false, 0, 0)

    const uRes = gl.getUniformLocation(prog, 'u_res')
    const uTime = gl.getUniformLocation(prog, 'u_time')
    const uMouse = gl.getUniformLocation(prog, 'u_mouse')

    const DPR = Math.min(window.devicePixelRatio || 1, 1.5)
    const RES = 0.7 // internal render scale — plasma is smooth, half-res is invisible and cheap
    function resize() {
      const w = Math.floor(window.innerWidth * DPR * RES)
      const h = Math.floor(window.innerHeight * DPR * RES)
      if (canvas!.width !== w || canvas!.height !== h) { canvas!.width = w; canvas!.height = h; gl!.viewport(0, 0, w, h) }
    }
    resize()
    window.addEventListener('resize', resize)

    const onMove = (e: PointerEvent) => {
      mouse.current.tx = (e.clientX / window.innerWidth - 0.5) * 2 * (window.innerWidth / window.innerHeight)
      mouse.current.ty = -(e.clientY / window.innerHeight - 0.5) * 2
    }
    window.addEventListener('pointermove', onMove, { passive: true })

    const start = performance.now()
    let raf = 0
    let last = 0
    let flow = 0                 // scroll-velocity accumulator — plasma surges on scroll
    let lastScroll = window.scrollY
    function frame(now: number) {
      raf = requestAnimationFrame(frame)
      // ~40fps cap — the motion is slow, saves GPU/battery
      if (now - last < 24) return
      last = now
      const sy = window.scrollY
      flow += Math.min(Math.abs(sy - lastScroll), 60) * 0.0009
      lastScroll = sy
      mouse.current.x += (mouse.current.tx - mouse.current.x) * 0.05
      mouse.current.y += (mouse.current.ty - mouse.current.y) * 0.05
      gl!.uniform2f(uRes, canvas!.width, canvas!.height)
      gl!.uniform1f(uTime, reduced ? 8.0 : (now - start) / 1000 + flow)
      gl!.uniform2f(uMouse, mouse.current.x, mouse.current.y)
      gl!.drawArrays(gl!.TRIANGLES, 0, 3)
      if (reduced) cancelAnimationFrame(raf) // single static frame
    }
    raf = requestAnimationFrame(frame)

    return () => {
      cancelAnimationFrame(raf)
      window.removeEventListener('resize', resize)
      window.removeEventListener('pointermove', onMove)
      gl.deleteProgram(prog); gl.deleteShader(vs); gl.deleteShader(fs); gl.deleteBuffer(buf)
    }
  }, [])

  return (
    <canvas
      ref={canvasRef}
      aria-hidden
      style={{ position: 'fixed', inset: 0, width: '100%', height: '100%', zIndex: 0, pointerEvents: 'none', display: 'block', background: '#06060e' }}
    />
  )
}
