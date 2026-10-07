"use client";

import { useId } from "react";
import { cn } from "@/lib/utils";

/** 静止的淳祐天文图式星图；径线、宿名与星官几何取自 World.dc。 */
export default function StarChart({ className }: { className?: string }) {
  const id = useId().replace(/:/g, "");
  return (
    <div className={cn("star-chart relative aspect-square shrink-0 pointer-events-none", className)}>
      <svg aria-hidden="true" viewBox="-34 -34 708 708" className="absolute inset-0 h-full w-full" style={{ opacity: "var(--art)" }}>
          <defs>
            <filter id={`${id}-yqw-rub`} x="0" y="0" width="100%" height="100%" colorInterpolationFilters="sRGB">
              <feTurbulence type="fractalNoise" baseFrequency="0.034" numOctaves="5" seed="5" result="n"></feTurbulence>
              <feColorMatrix in="n" type="matrix" values="0 0 0 0 1  0 0 0 0 1  0 0 0 0 1  3.4 0 0 0 -1.45" result="m"></feColorMatrix>
              <feTurbulence type="fractalNoise" baseFrequency="0.85" numOctaves="1" seed="12" result="g"></feTurbulence>
              <feColorMatrix in="g" type="matrix" values="0 0 0 0 1  0 0 0 0 1  0 0 0 0 1  0 0 0 7 -4.3" result="sp"></feColorMatrix>
              <feComposite in="m" in2="sp" operator="arithmetic" k2="1" k3="0.55" result="mm"></feComposite>
              <feComposite in="SourceGraphic" in2="mm" operator="in"></feComposite>
            </filter>
            <radialGradient id={`${id}-yqw-rub-fade`} gradientUnits="userSpaceOnUse" cx="320" cy="320" r="338">
              <stop offset="0" stopColor="#fff"></stop>
              <stop offset="0.86" stopColor="#fff"></stop>
              <stop offset="1" stopColor="#fff" stopOpacity="0"></stop>
            </radialGradient>
            <mask id={`${id}-yqw-rub-mk`} maskUnits="userSpaceOnUse" x="-34" y="-34" width="708" height="708"><rect x="-34" y="-34" width="708" height="708" fill={`url(#${id}-yqw-rub-fade)`}></rect></mask>
          </defs>
          {/* 盘心：外规以内一层薄釉色（昼如汝窑盘心积一汪天青，夜为拓片上墨最浓的一块）；有面积的色块过釉片口沿才看得出弯折与釉下虚影 */}
          <circle cx="320" cy="320" r="308" style={{"fill": "var(--disc)"}}></circle>
          <g mask={`url(#${id}-yqw-rub-mk)`}>
            <rect x="-34" y="-34" width="708" height="708" filter={`url(#${id}-yqw-rub)`} style={{"fill": "var(--rub)"}}></rect>
          </g>
          {/* 宿名带（r 308–330，在原外规之外补一道与内规同重的外框收口，带内填远山色）：石刻天文图最外一圈刻二十八宿名的环带。
               细线过口沿只剩断茬；这道有面积、有双框的环带横过热点釉片内沿与釉条上沿时，透镜把它折出错位，往里在釉下化成一圈虚影 */}
          <path d="M 320 -10 A 330 330 0 1 1 319.99 -10 Z M 320 12 A 308 308 0 1 0 320.01 12 Z" style={{"fill": "var(--m1)", "fillRule": "evenodd"}}></path>
          <circle cx="320" cy="320" r="330" style={{"fill": "none", "stroke": "var(--chart)", "strokeWidth": "1"}}></circle>
      </svg>
      <svg role="img" aria-label="星图" viewBox="-34 -34 708 708" className="absolute inset-0 h-full w-full">
          <defs>
            <clipPath id={`${id}-sky`}><circle cx="320" cy="320" r="300"></circle></clipPath>
          </defs>
          <g clipPath={`url(#${id}-sky)`}>
            <path d="M -20 130 C 110 175, 210 250, 325 292 C 440 334, 545 415, 670 520 L 670 600 C 545 495, 430 405, 315 362 C 200 320, 100 250, -20 205 Z" style={{"fill": "var(--river)"}}></path>
          </g>
          <circle cx="320" cy="320" r="308" style={{"fill": "none", "stroke": "var(--chartf)", "strokeWidth": "0.8"}}></circle>
          <circle cx="320" cy="320" r="300" style={{"fill": "none", "stroke": "var(--chart)", "strokeWidth": "1"}}></circle>
          <circle cx="320" cy="320" r="182" style={{"fill": "none", "stroke": "var(--chartf)", "strokeWidth": "0.8"}}></circle>
          <circle cx="344" cy="302" r="182" style={{"fill": "none", "stroke": "var(--chartf)", "strokeWidth": "0.8", "strokeDasharray": "3 4"}}></circle>
          <circle cx="320" cy="320" r="62" style={{"fill": "none", "stroke": "var(--chart)", "strokeWidth": "0.9"}}></circle>
          <g style={{"stroke": "var(--chartf)", "strokeWidth": "0.7"}}>
            <line x1="320" y1="258" x2="320" y2="20" transform="rotate(15 320 320)"></line>
            <line x1="320" y1="258" x2="320" y2="20" transform="rotate(26.8 320 320)"></line>
            <line x1="320" y1="258" x2="320" y2="20" transform="rotate(35.7 320 320)"></line>
            <line x1="320" y1="258" x2="320" y2="20" transform="rotate(50.5 320 320)"></line>
            <line x1="320" y1="258" x2="320" y2="20" transform="rotate(55.4 320 320)"></line>
            <line x1="320" y1="258" x2="320" y2="20" transform="rotate(60.3 320 320)"></line>
            <line x1="320" y1="258" x2="320" y2="20" transform="rotate(78.1 320 320)"></line>
            <line x1="320" y1="258" x2="320" y2="20" transform="rotate(88.9 320 320)"></line>
            <line x1="320" y1="258" x2="320" y2="20" transform="rotate(114.5 320 320)"></line>
            <line x1="320" y1="258" x2="320" y2="20" transform="rotate(122.4 320 320)"></line>
            <line x1="320" y1="258" x2="320" y2="20" transform="rotate(134.3 320 320)"></line>
            <line x1="320" y1="258" x2="320" y2="20" transform="rotate(144.1 320 320)"></line>
            <line x1="320" y1="258" x2="320" y2="20" transform="rotate(160.9 320 320)"></line>
            <line x1="320" y1="258" x2="320" y2="20" transform="rotate(176.6 320 320)"></line>
            <line x1="320" y1="258" x2="320" y2="20" transform="rotate(185.5 320 320)"></line>
            <line x1="320" y1="258" x2="320" y2="20" transform="rotate(201.3 320 320)"></line>
            <line x1="320" y1="258" x2="320" y2="20" transform="rotate(213.1 320 320)"></line>
            <line x1="320" y1="258" x2="320" y2="20" transform="rotate(226.9 320 320)"></line>
            <line x1="320" y1="258" x2="320" y2="20" transform="rotate(237.8 320 320)"></line>
            <line x1="320" y1="258" x2="320" y2="20" transform="rotate(253.5 320 320)"></line>
            <line x1="320" y1="258" x2="320" y2="20" transform="rotate(255.5 320 320)"></line>
            <line x1="320" y1="258" x2="320" y2="20" transform="rotate(264.4 320 320)"></line>
            <line x1="320" y1="258" x2="320" y2="20" transform="rotate(296.9 320 320)"></line>
            <line x1="320" y1="258" x2="320" y2="20" transform="rotate(300.8 320 320)"></line>
            <line x1="320" y1="258" x2="320" y2="20" transform="rotate(315.6 320 320)"></line>
            <line x1="320" y1="258" x2="320" y2="20" transform="rotate(322.5 320 320)"></line>
            <line x1="320" y1="258" x2="320" y2="20" transform="rotate(340.3 320 320)"></line>
            <line x1="320" y1="258" x2="320" y2="20" transform="rotate(358 320 320)"></line>
          </g>
          <g style={{"fill": "var(--ink2)", "fontFamily": "'Noto Serif SC', serif", "fontSize": "13px"}} textAnchor="middle" dominantBaseline="middle">
            <text x="320" y="2" transform="rotate(20.9 320 320)">角</text>
            <text x="320" y="2" transform="rotate(31.3 320 320)">亢</text>
            <text x="320" y="2" transform="rotate(43.1 320 320)">氐</text>
            <text x="320" y="2" transform="rotate(52.9 320 320)">房</text>
            <text x="320" y="2" transform="rotate(57.9 320 320)">心</text>
            <text x="320" y="2" transform="rotate(69.2 320 320)">尾</text>
            <text x="320" y="2" transform="rotate(83.5 320 320)">箕</text>
            <text x="320" y="2" transform="rotate(101.7 320 320)">斗</text>
            <text x="320" y="2" transform="rotate(118.5 320 320)">牛</text>
            <text x="320" y="2" transform="rotate(128.3 320 320)">女</text>
            <text x="320" y="2" transform="rotate(139.2 320 320)">虚</text>
            <text x="320" y="2" transform="rotate(152.5 320 320)">危</text>
            <text x="320" y="2" transform="rotate(168.8 320 320)">室</text>
            <text x="320" y="2" transform="rotate(181.1 320 320)">壁</text>
            <text x="320" y="2" transform="rotate(193.4 320 320)">奎</text>
            <text x="320" y="2" transform="rotate(207.2 320 320)">娄</text>
            <text x="320" y="2" transform="rotate(220 320 320)">胃</text>
            <text x="320" y="2" transform="rotate(232.3 320 320)">昴</text>
            <text x="320" y="2" transform="rotate(245.6 320 320)">毕</text>
            <text x="320" y="2" transform="rotate(254.5 320 320)">觜</text>
            <text x="320" y="2" transform="rotate(259.9 320 320)">参</text>
            <text x="320" y="2" transform="rotate(280.6 320 320)">井</text>
            <text x="320" y="2" transform="rotate(298.9 320 320)">鬼</text>
            <text x="320" y="2" transform="rotate(308.2 320 320)">柳</text>
            <text x="320" y="2" transform="rotate(319.1 320 320)">星</text>
            <text x="320" y="2" transform="rotate(331.4 320 320)">张</text>
            <text x="320" y="2" transform="rotate(349.1 320 320)">翼</text>
            <text x="320" y="2" transform="rotate(366.4 320 320)">轸</text>
          </g>
          <g style={{"fill": "none", "stroke": "var(--chart)", "strokeWidth": "0.7"}}>
            <polyline points="402.4,434.7 419.9,443.3 411.4,452.9"></polyline>
            <polyline points="469.7,390.3 457.6,386.2 434.4,376.1"></polyline>
            <polyline points="248.2,277.2 260.7,275.3 270.8,262.8"></polyline>
            <polyline points="375.6,193.9 391.6,205.9 396.7,218.3"></polyline>
            <polyline points="113.9,324.6 99.1,331.9 83.4,322.5 76.3,344.5 71.4,329.8"></polyline>
            <polyline points="286.2,59.7 276.1,51.4 261.8,50.3 248.1,71.3"></polyline>
            <polyline points="238.7,288.9 229.6,303.2 206.4,303.7 218.5,309.2"></polyline>
            <polyline points="310,236.3 294.4,215.6 301.4,201.2 285.3,215.3"></polyline>
            <polyline points="233.1,381.8 250.6,366.1 261,354.1 246.3,362.7"></polyline>
            <polyline points="366.1,412.3 359.5,402.1 366.6,389.4"></polyline>
            <polyline points="175.3,200.6 196,194.3 175.5,192.3 169.8,180.9"></polyline>
            <polyline points="397.7,69.4 383.7,79.9 366.2,81.9 375.6,105.9"></polyline>
            <polyline points="481.8,441.3 489.6,452.2 481.5,461.5 496,446.9 505.2,459.4"></polyline>
            <polyline points="376.5,241.1 360.3,243.1 374.1,260.8"></polyline>
            <polyline points="430,285.8 441.8,301.4 460.9,304.7 484.8,301.5"></polyline>
          </g>
          <g style={{"fill": "var(--ink)"}}>
            <circle cx="402.4" cy="434.7" r="2"></circle><circle cx="419.9" cy="443.3" r="2"></circle><circle cx="411.4" cy="452.9" r="2"></circle>
            <circle cx="469.7" cy="390.3" r="2"></circle><circle cx="457.6" cy="386.2" r="2"></circle><circle cx="434.4" cy="376.1" r="2"></circle>
            <circle cx="248.2" cy="277.2" r="2"></circle><circle cx="260.7" cy="275.3" r="2"></circle><circle cx="270.8" cy="262.8" r="2"></circle>
            <circle cx="375.6" cy="193.9" r="2"></circle><circle cx="391.6" cy="205.9" r="2"></circle><circle cx="396.7" cy="218.3" r="2"></circle>
            <circle cx="113.9" cy="324.6" r="2"></circle><circle cx="99.1" cy="331.9" r="2"></circle><circle cx="83.4" cy="322.5" r="2"></circle><circle cx="76.3" cy="344.5" r="2"></circle><circle cx="71.4" cy="329.8" r="2"></circle>
            <circle cx="286.2" cy="59.7" r="2"></circle><circle cx="276.1" cy="51.4" r="2"></circle><circle cx="261.8" cy="50.3" r="2"></circle><circle cx="248.1" cy="71.3" r="2"></circle>
            <circle cx="238.7" cy="288.9" r="2"></circle><circle cx="229.6" cy="303.2" r="2"></circle><circle cx="206.4" cy="303.7" r="2"></circle><circle cx="218.5" cy="309.2" r="2"></circle>
            <circle cx="310" cy="236.3" r="2"></circle><circle cx="294.4" cy="215.6" r="2"></circle><circle cx="301.4" cy="201.2" r="2"></circle><circle cx="285.3" cy="215.3" r="2"></circle>
            <circle cx="233.1" cy="381.8" r="2"></circle><circle cx="250.6" cy="366.1" r="2"></circle><circle cx="261" cy="354.1" r="2"></circle><circle cx="246.3" cy="362.7" r="2"></circle>
            <circle cx="366.1" cy="412.3" r="2"></circle><circle cx="359.5" cy="402.1" r="2"></circle><circle cx="366.6" cy="389.4" r="2"></circle>
            <circle cx="175.3" cy="200.6" r="2"></circle><circle cx="196" cy="194.3" r="2"></circle><circle cx="175.5" cy="192.3" r="2"></circle><circle cx="169.8" cy="180.9" r="2"></circle>
            <circle cx="397.7" cy="69.4" r="2"></circle><circle cx="383.7" cy="79.9" r="2"></circle><circle cx="366.2" cy="81.9" r="2"></circle><circle cx="375.6" cy="105.9" r="2"></circle>
            <circle cx="481.8" cy="441.3" r="2"></circle><circle cx="489.6" cy="452.2" r="2"></circle><circle cx="481.5" cy="461.5" r="2"></circle><circle cx="496" cy="446.9" r="2"></circle><circle cx="505.2" cy="459.4" r="2"></circle>
            <circle cx="376.5" cy="241.1" r="2"></circle><circle cx="360.3" cy="243.1" r="2"></circle><circle cx="374.1" cy="260.8" r="2"></circle>
            <circle cx="430" cy="285.8" r="2"></circle><circle cx="441.8" cy="301.4" r="2"></circle><circle cx="460.9" cy="304.7" r="2"></circle><circle cx="484.8" cy="301.5" r="2"></circle>
            <circle cx="399.3" cy="391.8" r="2.4"></circle><circle cx="320" cy="320" r="2.6"></circle>
          </g>
          <g style={{"fill": "var(--ink2)"}}>
            <circle cx="412" cy="480.2" r="1.1"></circle><circle cx="360.1" cy="102.8" r="1.3"></circle><circle cx="137.7" cy="162.8" r="1.1"></circle><circle cx="432.4" cy="74.5" r="1.1"></circle><circle cx="180.7" cy="326.3" r="0.9"></circle><circle cx="394.4" cy="31" r="1.6"></circle><circle cx="264.5" cy="173.1" r="1.3"></circle><circle cx="507.4" cy="241.7" r="1.3"></circle><circle cx="126.5" cy="540.5" r="1.1"></circle><circle cx="217.9" cy="339.4" r="1.3"></circle>
            <circle cx="219.9" cy="221" r="0.9"></circle><circle cx="199.8" cy="147.8" r="0.9"></circle><circle cx="520.3" cy="507.9" r="1.6"></circle><circle cx="320.2" cy="53.9" r="1.6"></circle><circle cx="60.8" cy="434.2" r="1.3"></circle><circle cx="411.7" cy="287.7" r="1.6"></circle><circle cx="311.4" cy="113.7" r="0.9"></circle><circle cx="443.5" cy="544.7" r="1.1"></circle><circle cx="265.3" cy="284.9" r="1.6"></circle><circle cx="483.9" cy="534.6" r="1.6"></circle>
            <circle cx="175.8" cy="517.4" r="1.1"></circle><circle cx="338.5" cy="262.2" r="0.9"></circle><circle cx="520.8" cy="231" r="1.6"></circle><circle cx="421.3" cy="600.3" r="1.1"></circle><circle cx="335.1" cy="383.6" r="1.1"></circle><circle cx="199.2" cy="553.6" r="1.6"></circle><circle cx="574.7" cy="422.5" r="1.3"></circle><circle cx="171.3" cy="77.4" r="1.6"></circle><circle cx="517.1" cy="130.6" r="1.1"></circle><circle cx="101.7" cy="287.5" r="0.9"></circle>
            <circle cx="366.5" cy="43.2" r="0.9"></circle><circle cx="476.1" cy="534.2" r="1.1"></circle><circle cx="287.6" cy="113.8" r="0.9"></circle><circle cx="146.4" cy="299.9" r="1.6"></circle><circle cx="529.4" cy="484.7" r="0.9"></circle><circle cx="294.1" cy="471.8" r="0.9"></circle><circle cx="120.2" cy="238.4" r="0.9"></circle><circle cx="166.3" cy="188.6" r="1.1"></circle><circle cx="80.4" cy="394" r="1.6"></circle><circle cx="323.2" cy="535.8" r="1.3"></circle>
          </g>
      </svg>
      <style jsx>{`
        .star-chart {
          --disc: rgba(147, 175, 164, .16);
          --rub: rgba(31, 41, 38, 0);
        }
        :global(.dark) .star-chart {
          --disc: rgba(0, 0, 0, .24);
          --rub: rgba(231, 227, 218, .06);
        }
      `}</style>
    </div>
  );
}
