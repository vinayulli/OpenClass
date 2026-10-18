import React, { useEffect, useRef, useState } from 'react';
import { ArrowDownRight, ArrowRight, BookOpen, BrainCircuit, Check, ChevronDown, ChevronRight, CircleHelp, ClipboardList, Clock3, Code2, Compass, FileText, GraduationCap, LayoutDashboard, LogOut, Plus, Search, Send, ShieldCheck, Sparkles, Users, X, Zap } from 'lucide-react';

export default function Stat({label,value,icon:Icon,note,tone}){return <article className="stat-card"><div className="stat-top"><span>{label}</span><span className={'stat-icon '+tone}><Icon size={19}/></span></div><strong>{value}</strong><p>{note}</p></article>}
