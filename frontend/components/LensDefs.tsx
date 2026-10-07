/** Document-local Chromium edge lenses. Safari/Firefox use the separate blur layer. */
export default function LensDefs() {
  return <svg aria-hidden="true" width="0" height="0" style={{position:"absolute",width:0,height:0,overflow:"hidden"}} dangerouslySetInnerHTML={{__html: `<defs>
      <filter id="yqd-lens" x="0" y="0" width="1" height="1" color-interpolation-filters="sRGB">
        <feFlood flood-color="#fff" result="f0"></feFlood>
        <feMorphology in="f0" operator="erode" radius="3" result="f"></feMorphology>
        <feGaussianBlur in="f" stdDeviation="7" result="a"></feGaussianBlur>
        <feOffset in="a" dx="-2" result="ax1"></feOffset>
        <feOffset in="a" dx="2" result="ax2"></feOffset>
        <feComposite in="ax1" in2="ax2" operator="arithmetic" k2="1.6" k3="-1.6" k4="0.5" result="gx"></feComposite>
        <feOffset in="a" dy="-2" result="ay1"></feOffset>
        <feOffset in="a" dy="2" result="ay2"></feOffset>
        <feComposite in="ay1" in2="ay2" operator="arithmetic" k2="1.6" k3="-1.6" k4="0.5" result="gy"></feComposite>
        <feColorMatrix in="gx" type="matrix" values="0 0 0 1 0  0 0 0 0 0  0 0 0 0 0  0 0 0 0 1" result="rx"></feColorMatrix>
        <feColorMatrix in="gy" type="matrix" values="0 0 0 0 0  0 0 0 1 0  0 0 0 0 0  0 0 0 0 1" result="ry"></feColorMatrix>
        <feComposite in="rx" in2="ry" operator="arithmetic" k2="1" k3="1" result="m0"></feComposite>
        <feGaussianBlur in="m0" stdDeviation="1.2" result="m1"></feGaussianBlur>
        <feColorMatrix in="m1" type="matrix" values="1 0 0 0 0  0 1 0 0 0  0 0 0 0 0.5  0 0 0 0 1" result="map"></feColorMatrix>
        <feDisplacementMap in="SourceGraphic" in2="map" scale="32" xChannelSelector="R" yChannelSelector="G"></feDisplacementMap>
      </filter>
      <filter id="yqd-lens-bar" x="0" y="0" width="1" height="1" color-interpolation-filters="sRGB">
        <feFlood flood-color="#fff" result="f0"></feFlood>
        <feMorphology in="f0" operator="erode" radius="3" result="f"></feMorphology>
        <feGaussianBlur in="f" stdDeviation="6" result="a"></feGaussianBlur>
        <feOffset in="a" dx="-2" result="ax1"></feOffset>
        <feOffset in="a" dx="2" result="ax2"></feOffset>
        <feComposite in="ax1" in2="ax2" operator="arithmetic" k2="1.6" k3="-1.6" k4="0.5" result="gx"></feComposite>
        <feOffset in="a" dy="-2" result="ay1"></feOffset>
        <feOffset in="a" dy="2" result="ay2"></feOffset>
        <feComposite in="ay1" in2="ay2" operator="arithmetic" k2="1.6" k3="-1.6" k4="0.5" result="gy"></feComposite>
        <feColorMatrix in="gx" type="matrix" values="0 0 0 1 0  0 0 0 0 0  0 0 0 0 0  0 0 0 0 1" result="rx"></feColorMatrix>
        <feColorMatrix in="gy" type="matrix" values="0 0 0 0 0  0 0 0 1 0  0 0 0 0 0  0 0 0 0 1" result="ry"></feColorMatrix>
        <feComposite in="rx" in2="ry" operator="arithmetic" k2="1" k3="1" result="m0"></feComposite>
        <feGaussianBlur in="m0" stdDeviation="1.2" result="m1"></feGaussianBlur>
        <feColorMatrix in="m1" type="matrix" values="1 0 0 0 0  0 1 0 0 0  0 0 0 0 0.5  0 0 0 0 1" result="map"></feColorMatrix>
        <feDisplacementMap in="SourceGraphic" in2="map" scale="20" xChannelSelector="R" yChannelSelector="G"></feDisplacementMap>
      </filter>
    
<filter id="yqm-lens" x="0" y="0" width="1" height="1" color-interpolation-filters="sRGB">
        <feFlood flood-color="#fff" result="f0"></feFlood>
        <feMorphology in="f0" operator="erode" radius="3" result="f"></feMorphology>
        <feGaussianBlur in="f" stdDeviation="7" result="a"></feGaussianBlur>
        <feOffset in="a" dx="-2" result="ax1"></feOffset>
        <feOffset in="a" dx="2" result="ax2"></feOffset>
        <feComposite in="ax1" in2="ax2" operator="arithmetic" k2="1.6" k3="-1.6" k4="0.5" result="gx"></feComposite>
        <feOffset in="a" dy="-2" result="ay1"></feOffset>
        <feOffset in="a" dy="2" result="ay2"></feOffset>
        <feComposite in="ay1" in2="ay2" operator="arithmetic" k2="1.6" k3="-1.6" k4="0.5" result="gy"></feComposite>
        <feColorMatrix in="gx" type="matrix" values="0 0 0 1 0  0 0 0 0 0  0 0 0 0 0  0 0 0 0 1" result="rx"></feColorMatrix>
        <feColorMatrix in="gy" type="matrix" values="0 0 0 0 0  0 0 0 1 0  0 0 0 0 0  0 0 0 0 1" result="ry"></feColorMatrix>
        <feComposite in="rx" in2="ry" operator="arithmetic" k2="1" k3="1" result="m0"></feComposite>
        <feGaussianBlur in="m0" stdDeviation="1.2" result="m1"></feGaussianBlur>
        <feColorMatrix in="m1" type="matrix" values="1 0 0 0 0  0 1 0 0 0  0 0 0 0 0.5  0 0 0 0 1" result="map"></feColorMatrix>
        <feDisplacementMap in="SourceGraphic" in2="map" scale="32" xChannelSelector="R" yChannelSelector="G"></feDisplacementMap>
      </filter>
<filter id="yqw-lens-chart" x="0" y="0" width="1" height="1" color-interpolation-filters="sRGB">
        <feFlood flood-color="#fff" result="f0"></feFlood>
        <feMorphology in="f0" operator="erode" radius="3" result="f"></feMorphology>
        <feGaussianBlur in="f" stdDeviation="14" result="a"></feGaussianBlur>
        <feOffset in="a" dx="-2" result="ax1"></feOffset>
        <feOffset in="a" dx="2" result="ax2"></feOffset>
        <feComposite in="ax1" in2="ax2" operator="arithmetic" k2="1.6" k3="-1.6" k4="0.5" result="gx"></feComposite>
        <feOffset in="a" dy="-2" result="ay1"></feOffset>
        <feOffset in="a" dy="2" result="ay2"></feOffset>
        <feComposite in="ay1" in2="ay2" operator="arithmetic" k2="1.6" k3="-1.6" k4="0.5" result="gy"></feComposite>
        <feColorMatrix in="gx" type="matrix" values="0 0 0 1 0  0 0 0 0 0  0 0 0 0 0  0 0 0 0 1" result="rx"></feColorMatrix>
        <feColorMatrix in="gy" type="matrix" values="0 0 0 0 0  0 0 0 1 0  0 0 0 0 0  0 0 0 0 1" result="ry"></feColorMatrix>
        <feComposite in="rx" in2="ry" operator="arithmetic" k2="1" k3="1" result="m0"></feComposite>
        <feGaussianBlur in="m0" stdDeviation="1.2" result="m1"></feGaussianBlur>
        <feColorMatrix in="m1" type="matrix" values="1 0 0 0 0  0 1 0 0 0  0 0 0 0 0.5  0 0 0 0 1" result="map"></feColorMatrix>
        <feDisplacementMap in="SourceGraphic" in2="map" scale="24" xChannelSelector="R" yChannelSelector="G"></feDisplacementMap>
      </filter>
<filter id="yqw-lens-bar" x="0" y="0" width="1" height="1" color-interpolation-filters="sRGB">
        <feFlood flood-color="#fff" result="f0"></feFlood>
        <feMorphology in="f0" operator="erode" radius="3" result="f"></feMorphology>
        <feGaussianBlur in="f" stdDeviation="6" result="a"></feGaussianBlur>
        <feOffset in="a" dx="-2" result="ax1"></feOffset>
        <feOffset in="a" dx="2" result="ax2"></feOffset>
        <feComposite in="ax1" in2="ax2" operator="arithmetic" k2="1.6" k3="-1.6" k4="0.5" result="gx"></feComposite>
        <feOffset in="a" dy="-2" result="ay1"></feOffset>
        <feOffset in="a" dy="2" result="ay2"></feOffset>
        <feComposite in="ay1" in2="ay2" operator="arithmetic" k2="1.6" k3="-1.6" k4="0.5" result="gy"></feComposite>
        <feColorMatrix in="gx" type="matrix" values="0 0 0 1 0  0 0 0 0 0  0 0 0 0 0  0 0 0 0 1" result="rx"></feColorMatrix>
        <feColorMatrix in="gy" type="matrix" values="0 0 0 0 0  0 0 0 1 0  0 0 0 0 0  0 0 0 0 1" result="ry"></feColorMatrix>
        <feComposite in="rx" in2="ry" operator="arithmetic" k2="1" k3="1" result="m0"></feComposite>
        <feGaussianBlur in="m0" stdDeviation="1.2" result="m1"></feGaussianBlur>
        <feColorMatrix in="m1" type="matrix" values="1 0 0 0 0  0 1 0 0 0  0 0 0 0 0.5  0 0 0 0 1" result="map"></feColorMatrix>
        <feDisplacementMap in="SourceGraphic" in2="map" scale="8" xChannelSelector="R" yChannelSelector="G"></feDisplacementMap>
      </filter></defs>`}} />;
}
