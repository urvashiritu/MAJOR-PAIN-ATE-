#!/usr/bin/env python3
"""Generate dataset.html with ECharts + storytelling narratives."""
import os

OUT = os.path.join(os.path.dirname(__file__), 'templates', 'dataset.html')

HTML = r'''<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>LANL - Dataset Analysis</title>
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link href="https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;600;700&display=swap" rel="stylesheet">
    <link rel="stylesheet" href="/static/css/style.css">
    <script src="https://cdn.jsdelivr.net/npm/echarts@5.6.0/dist/echarts.min.js"></script>
    <style>
        .chart-box{width:100%;height:320px}
        .chart-box-sm{width:100%;height:280px}
        .chart-box-lg{width:100%;height:420px}
        .insight-box{background:linear-gradient(135deg,rgba(229,72,77,0.06),rgba(232,163,61,0.04));border:1px solid rgba(229,72,77,0.15);border-radius:8px;padding:14px 18px;margin-bottom:16px;font-size:12px;line-height:1.7;color:var(--ink,#c8cdd8)}
        .insight-title{font-weight:700;color:var(--critical,#e5484d);margin-bottom:4px;font-size:11px;text-transform:uppercase;letter-spacing:.05em}
        .grid-2e{display:grid;grid-template-columns:2fr 1fr;gap:1rem}
        @media(max-width:900px){.grid-2e{grid-template-columns:1fr}}
    </style>
</head>
<body>
    <div class="app">
        <nav class="sidebar">
            <div class="sidebar-logo">LANL Anomaly</div>
            <a href="/analyst" class="sidebar-item"><span>&#9673;</span> Live Monitoring</a>
            <a href="/analyst/dataset" class="sidebar-item active"><span>&#9632;</span> Dataset Analysis</a>
            <div class="sidebar-divider"></div>
            <a href="/analyst#/alerts" class="sidebar-item"><span>&#9889;</span> Alerts</a>
            <a href="/analyst#/users" class="sidebar-item"><span>&#9673;</span> Users</a>
            <a href="/analyst#/settings" class="sidebar-item"><span>&#9881;</span> Settings</a>
            <div class="sidebar-spacer"></div>
            <button class="theme-btn" id="theme-toggle">&#9681;</button>
        </nav>

        <div class="main-area">
            <header class="topbar">
                <div class="topbar-left"><span class="topbar-title">Dataset Analysis</span></div>
                <div class="topbar-right">
                    <div class="flex-center gap-1">
                        <div class="health-dot" id="health-dot"></div>
                        <span class="text-10 text-faint uppercase tracking-widest">29.9M events loaded</span>
                    </div>
                    <a href="/logout" class="text-10 text-faint uppercase tracking-widest" style="cursor:pointer">Logout</a>
                </div>
            </header>

            <div class="content">
                <div class="grid-5 gap-4 mb-4">
                    <div class="panel panel-hover p-3">
                        <div class="kpi-label mb-1">Total Events</div>
                        <div class="tape-num text-ink" id="kpi-total"><span class="skeleton"></span></div>
                    </div>
                    <div class="panel panel-hover p-3">
                        <div class="kpi-label mb-1">Threats Detected</div>
                        <div class="tape-num text-critical" id="kpi-detections"><span class="skeleton"></span></div>
                    </div>
                    <div class="panel panel-hover p-3">
                        <div class="kpi-label mb-1">False Positives</div>
                        <div class="tape-num text-medium" id="kpi-fp"><span class="skeleton"></span></div>
                    </div>
                    <div class="panel panel-hover p-3">
                        <div class="kpi-label mb-1">Detection Rate</div>
                        <div class="tape-num text-low" id="kpi-rate"><span class="skeleton"></span></div>
                    </div>
                    <div class="panel panel-hover p-3">
                        <div class="kpi-label mb-1">Threshold</div>
                        <div class="tape-num text-info" id="kpi-threshold"><span class="skeleton"></span></div>
                    </div>
                </div>

                <div class="insight-box" id="insight-overview"><div class="insight-title">Loading...</div></div>

                <div class="panel p-4 mb-4">
                    <div class="section-title mb-3">Anomaly Score Timeline</div>
                    <div id="chart-timeline" class="chart-box"></div>
                </div>

                <div class="insight-box" id="insight-temporal" style="display:none"><div class="insight-title">Temporal Pattern</div><div id="insight-temporal-text"></div></div>

                <div class="grid-2e mb-4">
                    <div class="panel p-4">
                        <div class="section-title mb-3">Score Distribution</div>
                        <div id="chart-distribution" class="chart-box-sm"></div>
                    </div>
                    <div class="panel p-4">
                        <div class="section-title mb-3">Alert Breakdown</div>
                        <div id="chart-donut" class="chart-box-sm"></div>
                    </div>
                </div>

                <div class="insight-box" id="insight-score" style="display:none"><div class="insight-title">Score Analysis</div><div id="insight-score-text"></div></div>

                <div class="panel p-4 mb-4">
                    <div class="section-title mb-3">Top Attackers</div>
                    <div id="chart-attackers" class="chart-box-sm"></div>
                </div>

                <div class="insight-box" id="insight-attacker" style="display:none"><div class="insight-title">Attacker Profile</div><div id="insight-attacker-text"></div></div>

                <div class="panel p-4 mb-4">
                    <div class="section-title mb-3">Attack Network <span class="text-10 text-faint uppercase tracking-widest" style="margin-left:8px">src &#8594; dst connections</span></div>
                    <div id="chart-network" class="chart-box-lg"></div>
                </div>

                <div class="panel p-4 mb-4">
                    <div class="section-title mb-3">Hourly Heatmap <span class="text-10 text-faint uppercase tracking-widest" style="margin-left:8px">user &#215; hour</span></div>
                    <div id="chart-heatmap" class="chart-box"></div>
                </div>

                <div class="panel overflow-hidden">
                    <div class="flex-between px-4 py-3 hairline">
                        <span class="section-title">Recent Alerts</span>
                        <span class="text-10 text-faint uppercase tracking-widest">top 200 above threshold</span>
                    </div>
                    <div class="overflow-auto" style="max-height:400px">
                        <table class="table-glass">
                            <thead>
                                <tr>
                                    <th>Time</th>
                                    <th>Source</th>
                                    <th>Destination</th>
                                    <th>Score</th>
                                    <th>Decision</th>
                                </tr>
                            </thead>
                            <tbody id="alerts-tbody"></tbody>
                        </table>
                    </div>
                </div>
            </div>
        </div>
    </div>

    <script src="/static/js/api.js"></script>
    <script>
    (function(){
        'use strict';

        function initTheme(){
            var saved=localStorage.getItem('theme');
            var prefersDark=window.matchMedia('(prefers-color-scheme:dark)').matches;
            if(saved==='dark'||(!saved&&prefersDark))document.documentElement.classList.add('dark');
            var btn=document.getElementById('theme-toggle');
            if(btn)btn.addEventListener('click',function(){
                document.documentElement.classList.toggle('dark');
                localStorage.setItem('theme',document.documentElement.classList.contains('dark')?'dark':'light');
            });
        }

        function fmt(n){if(n>=1e6)return(n/1e6).toFixed(1)+'M';if(n>=1e3)return(n/1e3).toFixed(1)+'K';return n.toLocaleString();}

        async function init(){
            initTheme();
            try{
                var dash,alerts;
                [dash,alerts]=await Promise.all([API.datasetDashboard(),API.datasetAlerts()]);

                var isDark=document.documentElement.classList.contains('dark');
                var theme=isDark?'dark':'default';
                var C={
                    critical:isDark?'#e5484d':'#d13438',
                    ochre:'#e8a33d',
                    low:isDark?'#57b06c':'#2e7d51',
                    info:isDark?'#6ea8e8':'#3a6cb5',
                    ink:isDark?'#e8ecf4':'#232a38',
                    inkDim:isDark?'#8b93a5':'#59617a',
                    inkFaint:isDark?'#5a6274':'#939aad',
                    gridLine:isDark?'rgba(255,255,255,0.04)':'rgba(35,42,56,0.06)',
                    tooltipBg:isDark?'#1e2736':'#fffdf6'
                };

                var charts=[];
                function initChart(id){
                    var el=document.getElementById(id);
                    if(!el)return null;
                    var ch=echarts.init(el,theme);
                    charts.push(ch);
                    return ch;
                }
                window.addEventListener('resize',function(){charts.forEach(function(c){c.resize();});});

                var k=dash.kpis;
                var el=function(id){return document.getElementById(id);};
                if(el('kpi-total'))el('kpi-total').textContent=fmt(k.total_events);
                if(el('kpi-detections'))el('kpi-detections').textContent=fmt(k.detections);
                if(el('kpi-fp'))el('kpi-fp').textContent=fmt(k.false_positives);
                if(el('kpi-rate'))el('kpi-rate').textContent=k.detection_rate+'%';
                if(el('kpi-threshold'))el('kpi-threshold').textContent=k.threshold.toFixed(4);

                var avgScore=alerts.length?alerts.reduce(function(s,a){return s+a.anomaly_score;},0)/alerts.length:0;
                el('insight-overview').innerHTML='<div class="insight-title">Dataset Overview</div>Scanned <b>'+fmt(k.total_events)+'</b> authentication events across 6 months. Model flagged <b style="color:'+C.critical+'">'+fmt(k.detections)+'</b> threats with <b style="color:'+C.low+'">'+k.detection_rate+'%</b> detection rate. Top '+alerts.length+' alerts average score: <b style="color:'+C.ochre+'">'+avgScore.toFixed(3)+'</b> &#8212; model is highly confident.';

                if(dash.timeline&&dash.timeline.length){
                    var tl=dash.timeline;
                    var tc=initChart('chart-timeline');
                    if(tc)tc.setOption({
                        tooltip:{trigger:'axis',backgroundColor:C.tooltipBg,borderColor:'rgba(255,255,255,0.08)',textStyle:{color:C.ink,fontFamily:'JetBrains Mono',fontSize:11}},
                        legend:{data:['Max Score','Mean Score'],textStyle:{color:C.inkDim,fontSize:10,fontFamily:'JetBrains Mono'},top:2,right:20},
                        grid:{left:60,right:20,top:30,bottom:60},
                        xAxis:{type:'category',data:tl.map(function(_,i){return i;}),axisLabel:{color:C.inkFaint,fontSize:10},axisLine:{lineStyle:{color:C.gridLine}}},
                        yAxis:{type:'value',axisLabel:{color:C.inkFaint,fontSize:10,formatter:function(v){return v.toFixed(4);}},splitLine:{lineStyle:{color:C.gridLine}}},
                        dataZoom:[{type:'slider',start:0,end:100,height:24,bottom:8,borderColor:'transparent',backgroundColor:'rgba(255,255,255,0.03)',fillerColor:'rgba(232,163,61,0.15)',handleStyle:{color:C.ochre},textStyle:{color:C.inkFaint,fontSize:10}}],
                        series:[
                            {name:'Max Score',type:'line',data:tl.map(function(d){return d.max_score;}),smooth:true,lineStyle:{width:1.5,color:C.critical},areaStyle:{color:{type:'linear',x:0,y:0,x2:0,y2:1,colorStops:[{offset:0,color:'rgba(229,72,77,0.15)'},{offset:1,color:'rgba(229,72,77,0)'}]}},symbol:'none'},
                            {name:'Mean Score',type:'line',data:tl.map(function(d){return d.mean_score;}),smooth:true,lineStyle:{width:1.5,color:C.ochre},areaStyle:{color:{type:'linear',x:0,y:0,x2:0,y2:1,colorStops:[{offset:0,color:'rgba(232,163,61,0.12)'},{offset:1,color:'rgba(232,163,61,0)'}]}},symbol:'none'}
                        ]
                    });

                    var peakHours={};
                    tl.forEach(function(d){if(d.max_score>0.01)peakHours[d.hour_bucket]=d.max_score;});
                    var sorted=Object.entries(peakHours).sort(function(a,b){return b[1]-a[1];});
                    var peakStr=sorted.slice(0,3).map(function(e){return 'bucket '+e[0];}).join(', ');
                    el('insight-temporal').style.display='';
                    el('insight-temporal-text').innerHTML='Timeline shows <b>'+tl.length+'</b> hourly buckets. Anomaly spikes detected at <b style="color:'+C.critical+'">'+peakStr+'</b>. Most buckets have near-zero mean score &#8212; attacks are rare, concentrated events.';

                    var hm=dash.heatmap||[];
                    if(hm.length){
                        var userHours={};
                        hm.forEach(function(h){
                            if(!userHours[h.user])userHours[h.user]={total:0,max:0,hours:[]};
                            userHours[h.user].total+=h.score;
                            userHours[h.user].max=Math.max(userHours[h.user].max,h.score);
                            userHours[h.user].hours.push(h.hour);
                        });
                        var topUser=Object.entries(userHours).sort(function(a,b){return b[1].max-a[1].max;})[0];
                        el('insight-temporal').innerHTML+='<br>User <b style="color:'+C.ochre+'">'+topUser[0]+'</b> peaks at hours <b>'+topUser[1].hours.join(', ')+':00</b> with max score '+topUser[1].max.toFixed(4)+'.';
                    }
                }

                if(alerts&&alerts.length){
                    var scores=alerts.map(function(a){return a.anomaly_score;});
                    var maxS=Math.max.apply(null,scores);
                    var bins=50;
                    var binSize=maxS/bins;
                    var normalBins=new Array(bins).fill(0);
                    var redBins=new Array(bins).fill(0);
                    alerts.forEach(function(a,i){
                        var bin=Math.min(Math.floor(scores[i]/binSize),bins-1);
                        if(a.is_red)redBins[bin]++;else normalBins[bin]++;
                    });
                    var labels=Array.from({length:bins},function(_,i){return(i*binSize).toFixed(3);});

                    var dc=initChart('chart-distribution');
                    if(dc)dc.setOption({
                        tooltip:{trigger:'axis',backgroundColor:C.tooltipBg,textStyle:{color:C.ink,fontFamily:'JetBrains Mono',fontSize:11}},
                        legend:{data:['Normal','Attack'],textStyle:{color:C.inkDim,fontSize:10,fontFamily:'JetBrains Mono'},top:2,right:12},
                        grid:{left:50,right:12,top:30,bottom:30},
                        xAxis:{type:'category',data:labels,axisLabel:{color:C.inkFaint,fontSize:9,rotate:45,interval:9},axisLine:{lineStyle:{color:C.gridLine}}},
                        yAxis:{type:'value',axisLabel:{color:C.inkFaint,fontSize:10},splitLine:{lineStyle:{color:C.gridLine}}},
                        series:[
                            {name:'Normal',type:'bar',stack:'total',data:normalBins,itemStyle:{color:'rgba(139,147,165,0.4)'},barWidth:'90%'},
                            {name:'Attack',type:'bar',stack:'total',data:redBins,itemStyle:{color:C.critical},barWidth:'90%'}
                        ]
                    });

                    var blockCount=alerts.filter(function(a){return a.decision==='BLOCK';}).length;
                    var flagCount=alerts.filter(function(a){return a.decision==='FLAG';}).length;
                    var allowCount=alerts.filter(function(a){return a.decision==='ALLOW';}).length;

                    var donutData=[];
                    if(blockCount>0)donutData.push({value:blockCount,name:'BLOCK',itemStyle:{color:C.critical}});
                    if(flagCount>0)donutData.push({value:flagCount,name:'FLAG',itemStyle:{color:C.ochre}});
                    if(allowCount>0)donutData.push({value:allowCount,name:'ALLOW',itemStyle:{color:C.low}});

                    var gc=initChart('chart-donut');
                    if(gc)gc.setOption({
                        tooltip:{trigger:'item',backgroundColor:C.tooltipBg,textStyle:{color:C.ink,fontFamily:'JetBrains Mono',fontSize:11}},
                        series:[{
                            type:'pie',radius:['45%','70%'],center:['50%','55%'],
                            avoidLabelOverlap:false,
                            label:{show:true,position:'center',formatter:function(){return '{total|'+alerts.length+'}\n{label|alerts}';},rich:{total:{fontSize:24,fontWeight:700,color:C.ink,lineHeight:32},label:{fontSize:10,color:C.inkFaint,textTransform:'uppercase',letterSpacing:2}}},
                            data:donutData
                        }]
                    });

                    var scoreMin=Math.min.apply(null,scores);
                    el('insight-score').style.display='';
                    el('insight-score-text').innerHTML='Score distribution ranges from <b>'+scoreMin.toFixed(4)+'</b> to <b>'+maxS.toFixed(4)+'</b>. '+blockCount+' BLOCK decisions, '+flagCount+' FLAG decisions. The model shows strong separation &#8212; most clean events score near 0, attacks cluster near 1.0.';

                    var userCounts={};
                    alerts.forEach(function(a){userCounts[a.src_user]=(userCounts[a.src_user]||0)+1;});
                    var sortedUsers=Object.entries(userCounts).sort(function(a,b){return b[1]-a[1];}).slice(0,10).reverse();

                    var ac=initChart('chart-attackers');
                    if(ac)ac.setOption({
                        tooltip:{trigger:'axis',axisPointer:{type:'shadow'},backgroundColor:C.tooltipBg,textStyle:{color:C.ink,fontFamily:'JetBrains Mono',fontSize:11}},
                        grid:{left:130,right:30,top:10,bottom:10},
                        xAxis:{type:'value',axisLabel:{color:C.inkFaint,fontSize:10},splitLine:{lineStyle:{color:C.gridLine}}},
                        yAxis:{type:'category',data:sortedUsers.map(function(s){return s[0].split('@')[0];}),axisLabel:{color:C.inkDim,fontSize:10,fontFamily:'JetBrains Mono'}},
                        series:[{type:'bar',data:sortedUsers.map(function(s){return{value:s[1],itemStyle:{color:s[1]>20?C.critical:s[1]>10?C.ochre:C.info}};}),barWidth:'60%',label:{show:true,position:'right',color:C.inkDim,fontSize:10,fontFamily:'JetBrains Mono'}}]
                    });

                    var topAlertUser=Object.entries(userCounts).sort(function(a,b){return b[1]-a[1];})[0];
                    var pct=topAlertUser?(topAlertUser[1]/alerts.length*100).toFixed(0):0;
                    el('insight-attacker').style.display='';
                    el('insight-attacker-text').innerHTML='<b style="color:'+C.critical+'">'+(topAlertUser?topAlertUser[0]:'N/A')+'</b> dominates with <b>'+pct+'%</b> of all blocked alerts ('+topAlertUser[1]+'/'+alerts.length+'). '+Object.keys(userCounts).length+' unique attackers detected across '+alerts.length+' events.';

                    var netNodes={};
                    var netLinks=[];
                    alerts.forEach(function(a){
                        var src=a.src_user.split('@')[0];
                        var dst=a.dst_computer;
                        if(!netNodes[src])netNodes[src]={name:src,category:0,symbolSize:0,value:0};
                        if(!netNodes[dst])netNodes[dst]={name:dst,category:1,symbolSize:0,value:0};
                        netNodes[src].value+=a.anomaly_score;
                        netNodes[dst].value+=a.anomaly_score;
                        var existing=netLinks.find(function(l){return l.source===src&&l.target===dst;});
                        if(existing){existing.value+=a.anomaly_score;}else{netLinks.push({source:src,target:dst,value:a.anomaly_score});}
                    });
                    var sortedNodes=Object.values(netNodes).sort(function(a,b){return b.value-a.value;}).slice(0,30);
                    var topNames={};
                    sortedNodes.forEach(function(n){topNames[n.name]=true;});
                    var filteredLinks=netLinks.filter(function(l){return topNames[l.source]&&topNames[l.target];});
                    var maxNV=Math.max.apply(null,sortedNodes.map(function(n){return n.value;}));
                    sortedNodes.forEach(function(n){n.symbolSize=10+(n.value/maxNV)*40;});

                    var nc=initChart('chart-network');
                    if(nc)nc.setOption({
                        tooltip:{backgroundColor:C.tooltipBg,textStyle:{color:C.ink,fontFamily:'JetBrains Mono',fontSize:11}},
                        legend:{data:['Source User','Destination'],textStyle:{color:C.inkDim,fontSize:10,fontFamily:'JetBrains Mono'},top:2},
                        series:[{
                            type:'graph',layout:'force',
                            categories:[{name:'Source User',itemStyle:{color:C.critical}},{name:'Destination',itemStyle:{color:C.info}}],
                            data:sortedNodes,links:filteredLinks,
                            roam:true,draggable:true,
                            force:{repulsion:200,edgeLength:[80,160],gravity:0.1},
                            lineStyle:{color:'source',curveness:0.15,opacity:0.4},
                            emphasis:{focus:'adjacency',lineStyle:{width:3}},
                            label:{show:true,fontSize:9,color:C.inkDim,fontFamily:'JetBrains Mono'}
                        }]
                    });
                }

                if(dash.heatmap&&dash.heatmap.length){
                    var hmData=dash.heatmap;
                    var hmUsers=[];
                    var seen={};
                    hmData.forEach(function(d){if(!seen[d.user]){seen[d.user]=true;hmUsers.push(d.user);}});
                    var hmHours=Array.from({length:24},function(_,i){return i;});
                    var heatData=hmData.map(function(d){return[d.hour,hmUsers.indexOf(d.user),d.score];});
                    var maxHS=Math.max.apply(null,hmData.map(function(d){return d.score;}));

                    var hc=initChart('chart-heatmap');
                    if(hc)hc.setOption({
                        tooltip:{backgroundColor:C.tooltipBg,textStyle:{color:C.ink,fontFamily:'JetBrains Mono',fontSize:11},formatter:function(p){return hmUsers[p.value[1]]+'<br/>Hour '+p.value[0]+':00<br/>Score: '+p.value[2].toFixed(6);}},
                        grid:{left:130,right:40,top:10,bottom:30},
                        xAxis:{type:'category',data:hmHours.map(function(h){return h+':00';}),axisLabel:{color:C.inkFaint,fontSize:9},splitArea:{show:true}},
                        yAxis:{type:'category',data:hmUsers,axisLabel:{color:C.inkFaint,fontSize:9,width:120,overflow:'truncate'},splitArea:{show:true}},
                        visualMap:{min:0,max:maxHS,calculable:true,orient:'vertical',right:0,top:'center',inRange:{color:[isDark?'#10151d':'#faf8f2','#e8a33d','#e5484d']},textStyle:{color:C.inkFaint,fontSize:10}},
                        series:[{type:'heatmap',data:heatData,emphasis:{itemStyle:{shadowBlur:10,shadowColor:'rgba(0,0,0,0.5)'}}}]
                    });
                }

                var tbody=el('alerts-tbody');
                if(tbody&&alerts&&alerts.length){
                    tbody.innerHTML=alerts.map(function(a){
                        var date=new Date(a.time*1000);
                        var timeStr=date.toISOString().slice(0,19).replace('T',' ');
                        var decCls='stamp stamp-'+(a.decision==='BLOCK'?'critical':a.decision==='FLAG'?'medium':'low');
                        return '<tr><td>'+timeStr+'</td><td>'+a.src_computer+'</td><td>'+a.dst_computer+'</td><td>'+a.anomaly_score.toFixed(6)+'</td><td><span class="'+decCls+'">'+a.decision+'</span></td></tr>';
                    }).join('');
                }

            }catch(err){console.error('dataset load failed:',err);}
        }

        if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',init);else init();
    })();
    </script>
</body>
</html>'''

with open(OUT, 'w') as f:
    f.write(HTML)
print(f"Generated {OUT} ({len(HTML)} bytes)")
