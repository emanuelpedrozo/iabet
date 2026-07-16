import type {Config} from 'tailwindcss';
export default {content:['./app/**/*.{ts,tsx}','./components/**/*.{ts,tsx}'],theme:{extend:{colors:{ink:'#080d0b',panel:'#111916',line:'#26322d',brand:'#36e38b',muted:'#8ea39a'},boxShadow:{glow:'0 0 35px rgba(54,227,139,.12)'}}},plugins:[]} satisfies Config;
