        const xyzBasemap = "https://mapapi.geodata.gov.hk/gs/api/v1.0.0/xyz/basemap/WGS84/{z}/{x}/{y}.png"
        const xyzLabel = "https://mapapi.geodata.gov.hk/gs/api/v1.0.0/xyz/label/hk/en/WGS84/{z}/{x}/{y}.png"
        
        const venuePolygonApi = 'https://mapapi.hkmapservice.gov.hk/ogc/wfs/indoor/mtr_venue_polygon'
        const mapapiCredit = '<div style="display:flex"><a href="https://api.portal.hkmapservice.gov.hk/disclaimer" target="_blank">© Map information from Lands Department</a>&nbsp;<img style="height:20px;" src="https://api.hkmapservice.gov.hk/mapapi/landsdlogo.jpg"/></div>'
        
        const langs = ["EN", "繁"]
        let langIdx = 0
        
        const basemapProvider = new Cesium.UrlTemplateImageryProvider({
            url: xyzBasemap,
            credit: mapapiCredit,
        })
        const basemapLayer = new Cesium.ImageryLayer(basemapProvider)
        const viewer = new Cesium.Viewer('cesiumContainer', {
            baseLayer: basemapLayer,
            shadows: false,
            baseLayerPicker: false,
            sceneModePicker: false,
            fullscreenButton: false,
            timeline: false,
            animation: false,
            scene3DOnly: true,
            geocoder: false
        });
        
        document.querySelector(".cesium-widget-credits").innerHTML = basemapProvider.credit.html
        viewer.scene.imageryLayers.add(new Cesium.ImageryLayer(new Cesium.UrlTemplateImageryProvider({url:xyzLabel})));
        viewer.camera.setView({
            destination: Cesium.Cartesian3.fromDegrees(114.11602, 22.34563, 100000),
            orientation: {
                heading: Cesium.Math.toRadians(0.0),
                pitch: Cesium.Math.toRadians(-90),
            }
        });
        Cesium.Camera.DEFAULT_VIEW_RECTANGLE = Cesium.Rectangle.fromDegrees(113.78953, 22.20251, 114.44081, 22.49369)
        Cesium.Camera.DEFAULT_VIEW_FACTOR = 0;
        
        const handler = new Cesium.ScreenSpaceEventHandler(viewer.scene.canvas);
        let selectFeature = undefined
        let viewingVenueId = undefined
        let viewingVenueIndoor = undefined
        
        handler.setInputAction(async (movement) => {
            try{
                const picked = viewer.scene.pick(movement.position);
                if (!Cesium.defined(picked)) {
                    return;
                }
                selectFeature = picked.id
                const selectType = selectFeature.id.split('.')[0]
                switch(selectType){
                    case 'mtr_venue_polygon':
                    if(viewingVenueIndoor && viewingVenueId){
                        viewer.dataSources.getByName('mtr_venue_polygon')[0].entities.values.filter(e=>e.properties.venue_id == viewingVenueId).forEach(e=>e.show = true) // show all venue polygons
                        viewingVenueIndoor.destroy()
                    }
                    viewingVenueId = picked?.id.properties['venue_id']['_value']
                    viewingVenueIndoor = new MTRIndoor(viewer, viewingVenueId)
                    await viewingVenueIndoor.init()
                    viewingVenueIndoor.initVenueOption("#venueOption")
                    viewingVenueIndoor.flyTo()
                    viewingVenueIndoor.showAllFloor()
                    viewer.dataSources.getByName('mtr_venue_polygon')[0].entities.values.filter(e=>e.properties.venue_id == viewingVenueId).forEach(e=>e.show = false) // hide all venue polygons
                    break
                    case 'mtr_unit_polygon':
                    case 'mtr_opening_line':
                    case 'mtr_amenity_point':
                    case 'mtr_occupant_point':
                    let descHtml = `<table class="cesium-infoBox-defaultTable">`
                    picked.id?.properties.propertyNames.filter(pName => picked.id?.properties[pName]['_value']).forEach(pName => {
                        descHtml += `<tr><th>${pName}</th><td>
                        ${Array.isArray(picked.id?.properties[pName]['_value']) 
                        ? '<table class="cesium-infoBox-defaultTable"><tbody>' 
                        + picked.id?.properties[pName]['_value'].map((v,i)=>{return `<tr><th>${i}</th><td>${v}</td></tr>` }).join('')
                        + '</tbody></table>'
                        : picked.id?.properties[pName]}
                    </td></tr>`
                    })
                    descHtml += `</table>`
                    viewer.selectedEntity.description = descHtml
                    break
                    default:
                    break
                }
            }catch(ex){
                console.log('Rendering venue indoor not yet completed.', ex)
            }
        }, Cesium.ScreenSpaceEventType.LEFT_CLICK);
        
        class MTRIndoor {
            #version = 'v1.3.1'
            #indoorAPIs = {
                mtr_venue_polygon: 'https://mapapi.hkmapservice.gov.hk/ogc/wfs/indoor/mtr_venue_polygon',
                mtr_level_polygon: 'https://mapapi.hkmapservice.gov.hk/ogc/wfs/indoor/mtr_level_polygon',
                mtr_unit_polygon: 'https://mapapi.hkmapservice.gov.hk/ogc/wfs/indoor/mtr_unit_polygon',
                mtr_opening_line: 'https://mapapi.hkmapservice.gov.hk/ogc/wfs/indoor/mtr_opening_line',
                mtr_amenity_point : 'https://mapapi.hkmapservice.gov.hk/ogc/wfs/indoor/mtr_amenity_point',
                mtr_occupant_point : 'https://mapapi.hkmapservice.gov.hk/ogc/wfs/indoor/mtr_occupant_point',
            }
            #uniqueId = Math.random().toString(16).slice(2)
            #venueContainerId
            #cesiumViewer = undefined
            #venueId = ''
            #queryParam = ''
            #geoJson = {}
            #geoJsonDataSource = {}
            #customDataSource = {}
            #styles = {
                mtr_venue_polygon: { stroke: new Cesium.Color(0,0,0,0), fill: new Cesium.Color(0.82, 0.75, 0.99, 1), outline: false },
                mtr_level_polygon: { stroke: new Cesium.Color(0,0,0,0), fill: new Cesium.Color(0.96, 0.72, 0.99, 1), outline: false },
                mtr_unit_polygon: {
                    'default': { stroke: new Cesium.Color(0.7, 0.7, 0.7, 1), fill: new Cesium.Color(1, 0, 0, 1), outline: false },
                    'paidarea': { stroke: new Cesium.Color(0,0,0, 1), fill: new Cesium.Color(0.57, 0.73, 0.91, 1), outline: false },
                    'ticketing': { stroke: new Cesium.Color(0,0,0, 1), fill: new Cesium.Color(0.95, 0.91, 0.54, 1), outline: false }
                },
                mtr_amenity_point: { // Cesium.Billboard
                    'atm':{image:'https://mapapi.hkmapservice.gov.hk/resources/images/indoor/atm.svg',show:true,pixelOffset:new Cesium.Cartesian2(0,0),eyeOffset:new Cesium.Cartesian3(0.0,1.0,0.0),alignedAxis:Cesium.Cartesian3.ZERO,width:30,height:30,distanceDisplayCondition:new Cesium.DistanceDisplayCondition(0,350)},
                    'bank':{image:'https://mapapi.hkmapservice.gov.hk/resources/images/indoor/bank.svg',show:true,pixelOffset:new Cesium.Cartesian2(0,0),eyeOffset:new Cesium.Cartesian3(0.0,1.0,0.0),alignedAxis:Cesium.Cartesian3.ZERO,width:30,height:30,distanceDisplayCondition:new Cesium.DistanceDisplayCondition(0,350)},
                    'blooddonationcenter':{image:'https://mapapi.hkmapservice.gov.hk/resources/images/indoor/blooddonationcenter.svg',show:true,pixelOffset:new Cesium.Cartesian2(0,0),eyeOffset:new Cesium.Cartesian3(0.0,1.0,0.0),alignedAxis:Cesium.Cartesian3.ZERO,width:30,height:30,distanceDisplayCondition:new Cesium.DistanceDisplayCondition(0,350)},
                    'busstop':{image:'https://mapapi.hkmapservice.gov.hk/resources/images/indoor/busstop.svg',show:true,pixelOffset:new Cesium.Cartesian2(0,0),eyeOffset:new Cesium.Cartesian3(0.0,1.0,0.0),alignedAxis:Cesium.Cartesian3.ZERO,width:30,height:30,distanceDisplayCondition:new Cesium.DistanceDisplayCondition(0,350)},
                    'cinema':{image:'https://mapapi.hkmapservice.gov.hk/resources/images/indoor/cinema.svg',show:true,pixelOffset:new Cesium.Cartesian2(0,0),eyeOffset:new Cesium.Cartesian3(0.0,1.0,0.0),alignedAxis:Cesium.Cartesian3.ZERO,width:30,height:30,distanceDisplayCondition:new Cesium.DistanceDisplayCondition(0,350)},
                    'communitycenter':{image:'https://mapapi.hkmapservice.gov.hk/resources/images/indoor/communitycenter.svg',show:true,pixelOffset:new Cesium.Cartesian2(0,0),eyeOffset:new Cesium.Cartesian3(0.0,1.0,0.0),alignedAxis:Cesium.Cartesian3.ZERO,width:30,height:30,distanceDisplayCondition:new Cesium.DistanceDisplayCondition(0,350)},
                    'conveniencestore':{image:'https://mapapi.hkmapservice.gov.hk/resources/images/indoor/conveniencestore.svg',show:true,pixelOffset:new Cesium.Cartesian2(0,0),eyeOffset:new Cesium.Cartesian3(0.0,1.0,0.0),alignedAxis:Cesium.Cartesian3.ZERO,width:30,height:30,distanceDisplayCondition:new Cesium.DistanceDisplayCondition(0,350)},
                    'dancestudio':{image:'https://mapapi.hkmapservice.gov.hk/resources/images/indoor/dancestudio.svg',show:true,pixelOffset:new Cesium.Cartesian2(0,0),eyeOffset:new Cesium.Cartesian3(0.0,1.0,0.0),alignedAxis:Cesium.Cartesian3.ZERO,width:30,height:30,distanceDisplayCondition:new Cesium.DistanceDisplayCondition(0,350)},
                    'defibrillator':{image:'https://mapapi.hkmapservice.gov.hk/resources/images/indoor/aed.svg',show:true,pixelOffset:new Cesium.Cartesian2(0,0),eyeOffset:new Cesium.Cartesian3(0.0,1.0,0.0),alignedAxis:Cesium.Cartesian3.ZERO,width:30,height:30,distanceDisplayCondition:new Cesium.DistanceDisplayCondition(0,350)},
                    'elevator':{image:'https://mapapi.hkmapservice.gov.hk/resources/images/indoor/elevator.svg',show:true,pixelOffset:new Cesium.Cartesian2(0,0),eyeOffset:new Cesium.Cartesian3(0.0,1.0,0.0),alignedAxis:Cesium.Cartesian3.ZERO,width:30,height:30,distanceDisplayCondition:new Cesium.DistanceDisplayCondition(0,350)},
                    'entry':{image:'https://mapapi.hkmapservice.gov.hk/resources/images/indoor/entry.svg',show:true,pixelOffset:new Cesium.Cartesian2(0,0),eyeOffset:new Cesium.Cartesian3(0.0,1.0,0.0),alignedAxis:Cesium.Cartesian3.ZERO,width:30,height:30,distanceDisplayCondition:new Cesium.DistanceDisplayCondition(0,350)},
                    'escalator':{image:'https://mapapi.hkmapservice.gov.hk/resources/images/indoor/escalator.svg',show:true,pixelOffset:new Cesium.Cartesian2(0,0),eyeOffset:new Cesium.Cartesian3(0.0,1.0,0.0),alignedAxis:Cesium.Cartesian3.ZERO,width:30,height:30,distanceDisplayCondition:new Cesium.DistanceDisplayCondition(0,350)},
                    'eventspace':{image:'https://mapapi.hkmapservice.gov.hk/resources/images/indoor/eventspace.svg',show:true,pixelOffset:new Cesium.Cartesian2(0,0),eyeOffset:new Cesium.Cartesian3(0.0,1.0,0.0),alignedAxis:Cesium.Cartesian3.ZERO,width:30,height:30,distanceDisplayCondition:new Cesium.DistanceDisplayCondition(0,350)},
                    'faregate':{image:'https://mapapi.hkmapservice.gov.hk/resources/images/indoor/faregate.svg',show:true,pixelOffset:new Cesium.Cartesian2(0,0),eyeOffset:new Cesium.Cartesian3(0.0,1.0,0.0),alignedAxis:Cesium.Cartesian3.ZERO,width:30,height:30,distanceDisplayCondition:new Cesium.DistanceDisplayCondition(0,350)},
                    'fieldofplay':{image:'https://mapapi.hkmapservice.gov.hk/resources/images/indoor/fieldofplay.svg',show:true,pixelOffset:new Cesium.Cartesian2(0,0),eyeOffset:new Cesium.Cartesian3(0.0,1.0,0.0),alignedAxis:Cesium.Cartesian3.ZERO,width:30,height:30,distanceDisplayCondition:new Cesium.DistanceDisplayCondition(0,350)},
                    'foodstand':{image:'https://mapapi.hkmapservice.gov.hk/resources/images/indoor/foodstand.svg',show:true,pixelOffset:new Cesium.Cartesian2(0,0),eyeOffset:new Cesium.Cartesian3(0.0,1.0,0.0),alignedAxis:Cesium.Cartesian3.ZERO,width:30,height:30,distanceDisplayCondition:new Cesium.DistanceDisplayCondition(0,350)},
                    'gourmetmarket':{image:'https://mapapi.hkmapservice.gov.hk/resources/images/indoor/gourmetmarket.svg',show:true,pixelOffset:new Cesium.Cartesian2(0,0),eyeOffset:new Cesium.Cartesian3(0.0,1.0,0.0),alignedAxis:Cesium.Cartesian3.ZERO,width:30,height:30,distanceDisplayCondition:new Cesium.DistanceDisplayCondition(0,350)},
                    'gym':{image:'https://mapapi.hkmapservice.gov.hk/resources/images/indoor/gym.svg',show:true,pixelOffset:new Cesium.Cartesian2(0,0),eyeOffset:new Cesium.Cartesian3(0.0,1.0,0.0),alignedAxis:Cesium.Cartesian3.ZERO,width:30,height:30,distanceDisplayCondition:new Cesium.DistanceDisplayCondition(0,350)},
                    'information':{image:'https://mapapi.hkmapservice.gov.hk/resources/images/indoor/information.svg',show:true,pixelOffset:new Cesium.Cartesian2(0,0),eyeOffset:new Cesium.Cartesian3(0.0,1.0,0.0),alignedAxis:Cesium.Cartesian3.ZERO,width:30,height:30,distanceDisplayCondition:new Cesium.DistanceDisplayCondition(0,350)},
                    'library':{image:'https://mapapi.hkmapservice.gov.hk/resources/images/indoor/library.svg',show:true,pixelOffset:new Cesium.Cartesian2(0,0),eyeOffset:new Cesium.Cartesian3(0.0,1.0,0.0),alignedAxis:Cesium.Cartesian3.ZERO,width:30,height:30,distanceDisplayCondition:new Cesium.DistanceDisplayCondition(0,350)},
                    'mothersroom':{image:'https://mapapi.hkmapservice.gov.hk/resources/images/indoor/mothersroom.svg',show:true,pixelOffset:new Cesium.Cartesian2(0,0),eyeOffset:new Cesium.Cartesian3(0.0,1.0,0.0),alignedAxis:Cesium.Cartesian3.ZERO,width:30,height:30,distanceDisplayCondition:new Cesium.DistanceDisplayCondition(0,350)},
                    'movingwalkway':{image:'https://mapapi.hkmapservice.gov.hk/resources/images/indoor/movingwalkway.svg',show:true,pixelOffset:new Cesium.Cartesian2(0,0),eyeOffset:new Cesium.Cartesian3(0.0,1.0,0.0),alignedAxis:Cesium.Cartesian3.ZERO,width:30,height:30,distanceDisplayCondition:new Cesium.DistanceDisplayCondition(0,350)},
                    'parking':{image:'https://mapapi.hkmapservice.gov.hk/resources/images/indoor/parking.svg',show:true,pixelOffset:new Cesium.Cartesian2(0,0),eyeOffset:new Cesium.Cartesian3(0.0,1.0,0.0),alignedAxis:Cesium.Cartesian3.ZERO,width:30,height:30,distanceDisplayCondition:new Cesium.DistanceDisplayCondition(0,350)},
                    'parking.ev':{image:'https://mapapi.hkmapservice.gov.hk/resources/images/indoor/parking.ev.svg',show:true,pixelOffset:new Cesium.Cartesian2(0,0),eyeOffset:new Cesium.Cartesian3(0.0,1.0,0.0),alignedAxis:Cesium.Cartesian3.ZERO,width:30,height:30,distanceDisplayCondition:new Cesium.DistanceDisplayCondition(0,350)},
                    'parking.motorcycle':{image:'https://mapapi.hkmapservice.gov.hk/resources/images/indoor/parking.motorcycle.svg',show:true,pixelOffset:new Cesium.Cartesian2(0,0),eyeOffset:new Cesium.Cartesian3(0.0,1.0,0.0),alignedAxis:Cesium.Cartesian3.ZERO,width:30,height:30,distanceDisplayCondition:new Cesium.DistanceDisplayCondition(0,350)},
                    'performingarts':{image:'https://mapapi.hkmapservice.gov.hk/resources/images/indoor/performingarts.svg',show:true,pixelOffset:new Cesium.Cartesian2(0,0),eyeOffset:new Cesium.Cartesian3(0.0,1.0,0.0),alignedAxis:Cesium.Cartesian3.ZERO,width:30,height:30,distanceDisplayCondition:new Cesium.DistanceDisplayCondition(0,350)},
                    'platform':{image:'https://mapapi.hkmapservice.gov.hk/resources/images/indoor/platform.svg',show:true,pixelOffset:new Cesium.Cartesian2(0,0),eyeOffset:new Cesium.Cartesian3(0.0,1.0,0.0),alignedAxis:Cesium.Cartesian3.ZERO,width:30,height:30,distanceDisplayCondition:new Cesium.DistanceDisplayCondition(0,350)},
                    'police':{image:'https://mapapi.hkmapservice.gov.hk/resources/images/indoor/police.svg',show:true,pixelOffset:new Cesium.Cartesian2(0,0),eyeOffset:new Cesium.Cartesian3(0.0,1.0,0.0),alignedAxis:Cesium.Cartesian3.ZERO,width:30,height:30,distanceDisplayCondition:new Cesium.DistanceDisplayCondition(0,350)},
                    'publictransport':{image:'https://mapapi.hkmapservice.gov.hk/resources/images/indoor/publictransport.svg',show:true,pixelOffset:new Cesium.Cartesian2(0,0),eyeOffset:new Cesium.Cartesian3(0.0,1.0,0.0),alignedAxis:Cesium.Cartesian3.ZERO,width:30,height:30,distanceDisplayCondition:new Cesium.DistanceDisplayCondition(0,350)},
                    'rail.muni':{image:'https://mapapi.hkmapservice.gov.hk/resources/images/indoor/rail.muni.svg',show:true,pixelOffset:new Cesium.Cartesian2(0,0),eyeOffset:new Cesium.Cartesian3(0.0,1.0,0.0),alignedAxis:Cesium.Cartesian3.ZERO,width:30,height:30,distanceDisplayCondition:new Cesium.DistanceDisplayCondition(0,350)},
                    'ramp':{image:'https://mapapi.hkmapservice.gov.hk/resources/images/indoor/ramp.svg',show:true,pixelOffset:new Cesium.Cartesian2(0,0),eyeOffset:new Cesium.Cartesian3(0.0,1.0,0.0),alignedAxis:Cesium.Cartesian3.ZERO,width:30,height:30,distanceDisplayCondition:new Cesium.DistanceDisplayCondition(0,350)},
                    'reception.desk':{image:'https://mapapi.hkmapservice.gov.hk/resources/images/indoor/Reception.svg',show:true,pixelOffset:new Cesium.Cartesian2(0,0),eyeOffset:new Cesium.Cartesian3(0.0,1.0,0.0),alignedAxis:Cesium.Cartesian3.ZERO,width:30,height:30,distanceDisplayCondition:new Cesium.DistanceDisplayCondition(0,350)},
                    'restaurant':{image:'https://mapapi.hkmapservice.gov.hk/resources/images/indoor/restaurant.svg',show:true,pixelOffset:new Cesium.Cartesian2(0,0),eyeOffset:new Cesium.Cartesian3(0.0,1.0,0.0),alignedAxis:Cesium.Cartesian3.ZERO,width:30,height:30,distanceDisplayCondition:new Cesium.DistanceDisplayCondition(0,350)},
                    'restroom.female':{image:'https://mapapi.hkmapservice.gov.hk/resources/images/indoor/restroom.female.svg',show:true,pixelOffset:new Cesium.Cartesian2(0,0),eyeOffset:new Cesium.Cartesian3(0.0,1.0,0.0),alignedAxis:Cesium.Cartesian3.ZERO,width:30,height:30,distanceDisplayCondition:new Cesium.DistanceDisplayCondition(0,350)},
                    'restroom.male':{image:'https://mapapi.hkmapservice.gov.hk/resources/images/indoor/restroom.male.svg',show:true,pixelOffset:new Cesium.Cartesian2(0,0),eyeOffset:new Cesium.Cartesian3(0.0,1.0,0.0),alignedAxis:Cesium.Cartesian3.ZERO,width:30,height:30,distanceDisplayCondition:new Cesium.DistanceDisplayCondition(0,350)},
                    'restroom.unisex':{image:'https://mapapi.hkmapservice.gov.hk/resources/images/indoor/restroom.unisex.svg',show:true,pixelOffset:new Cesium.Cartesian2(0,0),eyeOffset:new Cesium.Cartesian3(0.0,1.0,0.0),alignedAxis:Cesium.Cartesian3.ZERO,width:30,height:30,distanceDisplayCondition:new Cesium.DistanceDisplayCondition(0,350)},
                    'restroom.wheelchair':{image:'https://mapapi.hkmapservice.gov.hk/resources/images/indoor/restroom.wheelchair.svg',show:true,pixelOffset:new Cesium.Cartesian2(0,0),eyeOffset:new Cesium.Cartesian3(0.0,1.0,0.0),alignedAxis:Cesium.Cartesian3.ZERO,width:30,height:30,distanceDisplayCondition:new Cesium.DistanceDisplayCondition(0,350)},
                    'security':{image:'https://mapapi.hkmapservice.gov.hk/resources/images/indoor/security.svg',show:true,pixelOffset:new Cesium.Cartesian2(0,0),eyeOffset:new Cesium.Cartesian3(0.0,1.0,0.0),alignedAxis:Cesium.Cartesian3.ZERO,width:30,height:30,distanceDisplayCondition:new Cesium.DistanceDisplayCondition(0,350)},
                    'seniorcenter':{image:'https://mapapi.hkmapservice.gov.hk/resources/images/indoor/seniorcenter.svg',show:true,pixelOffset:new Cesium.Cartesian2(0,0),eyeOffset:new Cesium.Cartesian3(0.0,1.0,0.0),alignedAxis:Cesium.Cartesian3.ZERO,width:30,height:30,distanceDisplayCondition:new Cesium.DistanceDisplayCondition(0,350)},
                    'shopping':{image:'https://mapapi.hkmapservice.gov.hk/resources/images/indoor/shopping.svg',show:true,pixelOffset:new Cesium.Cartesian2(0,0),eyeOffset:new Cesium.Cartesian3(0.0,1.0,0.0),alignedAxis:Cesium.Cartesian3.ZERO,width:30,height:30,distanceDisplayCondition:new Cesium.DistanceDisplayCondition(0,350)},
                    'stairs':{image:'https://mapapi.hkmapservice.gov.hk/resources/images/indoor/stairs.svg',show:true,pixelOffset:new Cesium.Cartesian2(0,0),eyeOffset:new Cesium.Cartesian3(0.0,1.0,0.0),alignedAxis:Cesium.Cartesian3.ZERO,width:30,height:30,distanceDisplayCondition:new Cesium.DistanceDisplayCondition(0,350)},
                    'supermarket':{image:'https://mapapi.hkmapservice.gov.hk/resources/images/indoor/supermarket.svg',show:true,pixelOffset:new Cesium.Cartesian2(0,0),eyeOffset:new Cesium.Cartesian3(0.0,1.0,0.0),alignedAxis:Cesium.Cartesian3.ZERO,width:30,height:30,distanceDisplayCondition:new Cesium.DistanceDisplayCondition(0,350)},
                    'swimmingpool':{image:'https://mapapi.hkmapservice.gov.hk/resources/images/indoor/swimmingpool.svg',show:true,pixelOffset:new Cesium.Cartesian2(0,0),eyeOffset:new Cesium.Cartesian3(0.0,1.0,0.0),alignedAxis:Cesium.Cartesian3.ZERO,width:30,height:30,distanceDisplayCondition:new Cesium.DistanceDisplayCondition(0,350)},
                    'taxi':{image:'https://mapapi.hkmapservice.gov.hk/resources/images/indoor/taxi.svg',show:true,pixelOffset:new Cesium.Cartesian2(0,0),eyeOffset:new Cesium.Cartesian3(0.0,1.0,0.0),alignedAxis:Cesium.Cartesian3.ZERO,width:30,height:30,distanceDisplayCondition:new Cesium.DistanceDisplayCondition(0,350)},
                    'trainstation':{image:'https://mapapi.hkmapservice.gov.hk/resources/images/indoor/trainstation.svg',show:true,pixelOffset:new Cesium.Cartesian2(0,0),eyeOffset:new Cesium.Cartesian3(0.0,1.0,0.0),alignedAxis:Cesium.Cartesian3.ZERO,width:30,height:30,distanceDisplayCondition:new Cesium.DistanceDisplayCondition(0,350)},
                    'travelagent':{image:'https://mapapi.hkmapservice.gov.hk/resources/images/indoor/travelagent.svg',show:true,pixelOffset:new Cesium.Cartesian2(0,0),eyeOffset:new Cesium.Cartesian3(0.0,1.0,0.0),alignedAxis:Cesium.Cartesian3.ZERO,width:30,height:30,distanceDisplayCondition:new Cesium.DistanceDisplayCondition(0,350)},
                    'vendingmachine':{image:'https://mapapi.hkmapservice.gov.hk/resources/images/indoor/vendingmachine.svg',show:true,pixelOffset:new Cesium.Cartesian2(0,0),eyeOffset:new Cesium.Cartesian3(0.0,1.0,0.0),alignedAxis:Cesium.Cartesian3.ZERO,width:30,height:30,distanceDisplayCondition:new Cesium.DistanceDisplayCondition(0,350)},
                    'wheelchairassist':{image:'https://mapapi.hkmapservice.gov.hk/resources/images/indoor/stairlift.svg',show:true,pixelOffset:new Cesium.Cartesian2(0,0),eyeOffset:new Cesium.Cartesian3(0.0,1.0,0.0),alignedAxis:Cesium.Cartesian3.ZERO,width:30,height:30,distanceDisplayCondition:new Cesium.DistanceDisplayCondition(0,350)}
                },
                mtr_occupant_point: {// Cesium.LabelGraphics
                    font: 'Arial', eyeOffset: new Cesium.Cartesian3(0.0, 1.0, 0.0), 
                    fillColor : Cesium.Color.BLACK , outlineColor : Cesium.Color.WHITE,
                    outlineWidth: 5, style: Cesium.LabelStyle.FILL_AND_OUTLINE
                }, 
                
                
            }
            constructor(cesiumViewer, venueId) { 
                this.#queryParam = `?service=WFS&version=2.0.0&request=GetFeature&outputFormat=application%2Fjson&srsname=EPSG:4326&count=5000&cql_filter=venue_id%3D'${venueId}'`
                this.#cesiumViewer = cesiumViewer
                this.#venueId = venueId
            }
            async init() {
                Object.keys(this.#indoorAPIs).forEach((featureCategory) => {
                    if (['mtr_unit_polygon','mtr_amenity_point'].includes(featureCategory)){
                        this.#geoJsonDataSource[featureCategory] = {}
                        Object.keys(this.#styles[featureCategory]).forEach(dataCategory => {
                            this.#geoJsonDataSource[featureCategory][dataCategory] = new Cesium.GeoJsonDataSource(`${this.#uniqueId}_${featureCategory}_${dataCategory}`)     
                        })
                    } 
                    else{
                        this.#geoJsonDataSource[featureCategory] = new Cesium.GeoJsonDataSource(`${this.#uniqueId}_${featureCategory}`) 
                    }
                })
                const results = await Promise.all(Object.keys(this.#indoorAPIs).map(key => fetch(`${this.#indoorAPIs[key]}${this.#queryParam}`)))
                const values = await Promise.all(results.map(p => p.json()))
                let i = 0;
                Object.keys(this.#indoorAPIs).forEach((featureCategory) => {
                    const _geoJson = values[i++]
                    this.#geoJson[featureCategory] = _geoJson
                    if (['mtr_unit_polygon','mtr_amenity_point'].includes(featureCategory)){
                        Object.keys(this.#styles[featureCategory]).forEach(dataCategory => {
                            this.#cesiumViewer.dataSources.add(this.#geoJsonDataSource[featureCategory][dataCategory])
                        })
                    }else{
                        this.#cesiumViewer.dataSources.add(this.#geoJsonDataSource[featureCategory])}
                    })
                    this.#customDataSource = {
                        "Opening" : new Cesium.CustomDataSource('Opening'),
                        "Amenity" : new Cesium.CustomDataSource('Amenity'),
                        "Occupant" : new Cesium.CustomDataSource('Occupant'),
                        
                    }
                    Object.values(this.#customDataSource).forEach((dsCustom) => {
                        this.#cesiumViewer.dataSources.add(dsCustom)
                    })
                }
                async showAllFloor() {
                    Object.values(this.#customDataSource).forEach((dsCustom) => {
                        dsCustom.entities.removeAll()
                    })
                    Object.keys(this.#indoorAPIs).forEach((cate) => {
                        this.showByCategory(cate, this.#geoJson[cate])
                    })
                }
                async showFloor(floor) {
                    Object.values(this.#customDataSource).forEach((dsCustom) => {
                        dsCustom.entities.removeAll()
                    })
                    Object.keys(this.#indoorAPIs).forEach((cate) => {
                        const clone = structuredClone(this.#geoJson[cate]) 
                        clone.features = clone.features.filter(f => f.properties.level_short_name_en == floor)
                        this.showByCategory(cate, clone)
                    })
                }
                async showFloorWithLower(ordinal) {
                    Object.values(this.#customDataSource).forEach((dsCustom) => {
                        dsCustom.entities.removeAll()
                    })
                    Object.keys(this.#indoorAPIs).forEach((cate) => {
                        const clone = structuredClone(this.#geoJson[cate]) 
                        clone.features = clone.features.filter(f => parseInt(f.properties.level_ordinal) <= parseInt(ordinal))
                        this.showByCategory(cate, clone)
                    })
                }
                async showByCategory(featureCategory, geojson) {
                    switch (featureCategory) {
                        case "mtr_venue_polygon":
                        case "mtr_level_polygon":
                        break
                        case "mtr_opening_line":
                        await this.#geoJsonDataSource[featureCategory].load(geojson, this.#styles[featureCategory])
                        this.#geoJsonDataSource[featureCategory].show = false
                        for (const entity of this.#geoJsonDataSource[featureCategory].entities.values) {
                            if (entity.properties.opening_door_type == 'sliding' || entity.properties.opening_category == 'pedestrian.principal') {
                                const baseHeight = parseFloat(entity.properties.level_z_value)
                                const corr = {
                                    id : `${featureCategory}.${Math.random().toString(16).slice(2)}`,
                                    name: entity.properties.opening_door_type,
                                    corridor: {
                                        positions: entity.polyline.positions,
                                        height: baseHeight,
                                        extrudedHeight: baseHeight + 0.05,
                                        width: 0.12,
                                        material: entity.properties.opening_category == 'pedestrian.principal' ? new Cesium.Color(0.78, 0.34, 0.17, 1) : new Cesium.Color(0, 0.35, 0.57, 1),
                                        outline: false,
                                        cornerType: Cesium.CornerType.MITERED
                                    },  
                                    properties: entity.properties
                                }
                                this.#customDataSource.Opening.entities.add(corr)
                            }
                        }
                        break
                        case "mtr_unit_polygon":
                        Object.keys(this.#styles[featureCategory]).forEach(async dataCategory =>{
                            const clone = structuredClone(geojson)
                            if (dataCategory == 'paidarea' || dataCategory == 'ticketing'){
                                clone.features = clone.features.filter(f => f.properties.section_category && f.properties.section_category.toLowerCase() == dataCategory)
                            }else{
                                clone.features = clone.features.filter(f => (!f.properties.section_category || (f.properties.section_category.toLowerCase() != 'paidarea' && f.properties.section_category.toLowerCase() != 'ticketing')))
                            }
                            await this.#geoJsonDataSource[featureCategory][dataCategory].load(clone, this.#styles[featureCategory][dataCategory])
                            Object.values(this.#geoJsonDataSource[featureCategory][dataCategory].entities.values).map(entity => {
                                entity.name = entity.properties.getValue().occupant_name_en ? entity.properties.getValue().occupant_name_en :entity.properties.getValue().unit_name_en         
                                entity.polygon.arcType = Cesium.ArcType.GEODESIC
                                entity.polygon.height = parseFloat(entity.properties.level_z_value)
                                entity.polygon.extrudedHeight = parseFloat(entity.properties.level_z_value) + parseFloat(entity.properties.unit_display_thickness)
                            })
                        })
                        break
                        case "mtr_amenity_point": 
                        const dsAmenity = this.#customDataSource.Amenity
                        console.log(dsAmenity)
                        Object.keys(this.#styles[featureCategory]).forEach(async dataCategory =>{
                            const clone = structuredClone(geojson)
                            clone.features = geojson.features.filter(f => f.properties.amenity_category == dataCategory)
                            await this.#geoJsonDataSource[featureCategory][dataCategory].load(clone) 
                            this.#geoJsonDataSource[featureCategory][dataCategory].show = false
                            for (const entity of this.#geoJsonDataSource[featureCategory][dataCategory].entities.values) {
                                const amenityPoint = {
                                    id: `${featureCategory}.${Math.random().toString(16).slice(2)}`,
                                    name: entity.properties.amenity_name_en,
                                    position: entity.position,
                                    billboard : this.#styles[featureCategory][dataCategory],
                                    properties: entity.properties
                                }
                                dsAmenity.entities.add(amenityPoint);
                                
                                if (entity.properties['amenity_category']=="platform" || entity.properties['amenity_category']=="entry"){
                                    const lblStyle = structuredClone(this.#styles['mtr_occupant_point'])
                                    lblStyle.pixelOffset = new Cesium.Cartesian3(0,-28)
                                    lblStyle.text = langIdx == 0 ? entity.properties['amenity_name_en']._value : entity.properties['amenity_name_zh']._value
                                    lblStyle.distanceDisplayCondition = new Cesium.DistanceDisplayCondition(0, 350)
                                    const amenityPoint_lbl = {
                                        id: `${featureCategory}.${Math.random().toString(16).slice(2)}`,
                                        name: entity.properties.amenity_name_en,
                                        position: entity.position,
                                        label: lblStyle,
                                        properties: entity.properties,
                                    }
                                    
                                    dsAmenity.entities.add(amenityPoint_lbl);
                                }
                                
                            }
                        })
                        break
                        case "mtr_occupant_point":
                        const dsOccupant = this.#customDataSource.Occupant
                        await this.#geoJsonDataSource[featureCategory].load(geojson, this.#styles[featureCategory])
                        this.#geoJsonDataSource[featureCategory].show = false
                        for (const entity of this.#geoJsonDataSource[featureCategory].entities.values) {
                            const lblStyle = structuredClone(this.#styles[featureCategory])
                            lblStyle.text = langIdx == 0 ? entity.properties['occupant_name_en']._value : entity.properties['occupant_name_zh']._value
                            lblStyle.distanceDisplayCondition = new Cesium.DistanceDisplayCondition(0, 350)
                            const lbl = {
                                id : `${featureCategory}.${Math.random().toString(16).slice(2)}`,
                                name : entity.properties.occupant_name_en,
                                position : entity.position,
                                label : lblStyle,  
                                properties: entity.properties,
                            }
                            dsOccupant.entities.add(lbl);
                        }
                        break
                        default:
                        this.#geoJsonDataSource[featureCategory].load(geojson, this.#styles[featureCategory])
                    }
                }
                removeAllFloor() {
                    Object.values(this.#customDataSource).forEach((dsCustom) => {
                        dsCustom.entities.removeAll()
                    })
                    Object.keys(this.#indoorAPIs).forEach((featureCategory) => {
                        const clone = structuredClone(this.#geoJson[featureCategory])
                        clone.features = []
                        if(['mtr_unit_polygon','mtr_amenity_point'].includes(featureCategory)){
                            Object.keys(this.#styles[featureCategory]).forEach(unitCate =>{
                                this.#geoJsonDataSource[featureCategory][unitCate].load(clone, this.#styles[featureCategory][unitCate])
                            })
                        }else
                            this.#geoJsonDataSource[featureCategory].load(clone, this.#styles[featureCategory])
                    })
                }
                initVenueOption(containerId) {
                    const floorSelectId = `floor-selection`
                    const toggleLowerId = `floor-mode-toggle`
                    
                    this.#venueContainerId = containerId
                    const container = document.querySelector(containerId)
                    
                    let tempHtml = `<table class="infoPanel">
                    <thead><tr><th colspan=2>${this.#geoJson['mtr_venue_polygon'].features[0].properties.venue_name_en}</th></tr></thread>
                    <tbody>
                        <tr><td><label for="${toggleLowerId}" style="cursor:pointer">With lower floor</label></td><td><input type="checkbox" id="${toggleLowerId}" /></td></tr>
                        </tbody></table>`;
                    tempHtml += `<div id="${floorSelectId}" class="infoPanel"><div data-floor="All" data-value="All" selected class="active">All</div></div>`
                    container.innerHTML = tempHtml
                    const floorSelect = document.querySelector(`#${floorSelectId}`)
                    const toggleLower = document.querySelector(`#${toggleLowerId}`)
                    const levelList = this.#geoJson['mtr_level_polygon'].features
                    const lvDict = {}         
                    levelList.forEach((floor) => {
                        if (!lvDict[floor.properties.level_short_name_en]){
                            lvDict[floor.properties.level_short_name_en] = {min: 999, max:-999}
                        }
                        lvDict[floor.properties.level_short_name_en] = {
                            min: Math.min(lvDict[floor.properties.level_short_name_en].min, parseInt(floor.properties.level_ordinal)),
                            max: Math.max(lvDict[floor.properties.level_short_name_en].max, parseInt(floor.properties.level_ordinal))
                        }
                    })
                    const lvDisplay = Object.entries(lvDict)
                    lvDisplay.sort((a,b)=>{
                        return b[1].min - a[1].min
                    })
                    
                    lvDisplay.forEach((floor) => {
                        const floorDis = floor[0]
                        const floorOrdMin = floor[1].min
                        const floorOrdMax = floor[1].max
                        const opt = document.createElement('div')
                        opt.dataset.floor = floorDis
                        opt.innerHTML = floorDis
                        opt.dataset.ordinalMin = floorOrdMin
                        opt.dataset.ordinalMax = floorOrdMax
                        floorSelect.appendChild(opt)
                    })
                    const updateFloor = async (floor, ordinal, withLower) => {
                        floor == 'All' ? this.showAllFloor() : (withLower ? this.showFloorWithLower(ordinal) : this.showFloor(floor))
                    }
                    document.querySelectorAll(`#${floorSelectId} > div`).forEach(ele => {
                        ele.addEventListener('click', async event => {
                            document.querySelectorAll(`#${floorSelectId} > div.active`).forEach(e => e.classList.remove('active'))
                            ele.classList.add("active")
                            updateFloor(event.target.dataset.floor, event.target.dataset.ordinalMax, toggleLower.checked)
                        })
                    })
                    toggleLower.addEventListener('change', async event => {
                        const selected = document.querySelectorAll(`#${floorSelectId} > div.active`)[0]
                        updateFloor(selected.dataset.floor, selected.dataset.ordinalMax, event.target.checked)
                    })
                }
                async deleteVenueOption() {
                    document.querySelector(this.#venueContainerId).innerHTML = ''
                }
                async flyTo() {
                    const paidareaUnits = this.#geoJson['mtr_unit_polygon'].features.filter(unit=>unit.properties.section_category?.toLowerCase() == 'paidarea')
                    const paidarea = [1e10,1e10,-1e10,-1e10]
                    let zMin = 1e10
                    let zMax = -1e10
                    paidareaUnits.forEach(unit=>{
                        const bbox = unit.properties.bbox
                        paidarea[0] = Math.min(paidarea[0], parseFloat(bbox[0]))
                        paidarea[1] = Math.min(paidarea[1], parseFloat(bbox[1]))
                        paidarea[2] = Math.max(paidarea[2], parseFloat(bbox[2]))
                        paidarea[3] = Math.max(paidarea[3], parseFloat(bbox[3]))
                        zMin = Math.min(zMin, parseFloat(unit.properties.level_z_value))
                        zMax = Math.max(zMax, parseFloat(unit.properties.level_z_value))
                    })
                    const center = Cesium.Cartesian3.fromDegrees((paidarea[0] + paidarea[2]) / 2, (paidarea[1] + paidarea[3]) / 2 , (zMin+ zMax)/2)
                    const min3D = Cesium.Cartesian3.fromDegrees(paidarea[0], paidarea[1], zMin)
                    const max3D = Cesium.Cartesian3.fromDegrees(paidarea[2], paidarea[3], zMax)
                    const r = Cesium.Cartesian3.distance(max3D, min3D) / 2
                    const heading = Math.atan(9/16) - Math.atan((paidarea[3]-paidarea[1]) / (paidarea[2]-paidarea[0]))
                    const pitch = -Math.atan(9/16)
                    this.#cesiumViewer.camera.flyToBoundingSphere(new Cesium.BoundingSphere(center, r), {
                        offset: {
                            heading: heading, 
                            pitch: pitch, 
                            range: Math.min(2 * r, 200)
                        }
                    })
                }
                destroy() {
                    this.removeAllFloor()
                    this.deleteVenueOption()
                    this.#geoJson = {}
                    this.#geoJsonDataSource = {}
                }
            }
            
            const addLanaguage = ()=>{
                const langBtn = document.createElement("button")
                langBtn.classList.add("cesium-button", "cesium-toolbar-button")
                langBtn.style.fontSize = "16px"
                langBtn.innerText = langs[langIdx]
                document.querySelector(".cesium-home-button").before(langBtn)
                const changeLanguage = ()=>{
    langIdx = 1 - langIdx
    langBtn.innerText = langs[langIdx]
    console.log(viewer.dataSources)
    
    // Update Occupant Label
    viewer.dataSources.getByName("Occupant")?.forEach(occDS =>{
        for (let i =0; i< occDS.entities.values.length; i++){
            const ent = occDS.entities.getById(occDS.entities.values[i].id)
            ent.label.text = langIdx == 0 ? ent.properties['occupant_name_en']._value : ent.properties['occupant_name_zh']._value
        }
    })
    
    // Update Amenity Entry Label
    viewer.dataSources.getByName("Amenity")?.forEach(amenityDS => {
        for (let i =0; i< amenityDS.entities.values.length; i++){
            const ent = amenityDS.entities.getById(amenityDS.entities.values[i].id)
            if (ent.label)
                ent.label.text = langIdx == 0 ? ent.properties['amenity_name_en']._value : ent.properties['amenity_name_zh']._value
        }
    })

    // --- 新增：更新地鐵站外觀 (Venue) 的語言 ---
    viewer.dataSources.getByName("mtr_venue_polygon")?.forEach(venueDS => {
        for (let i = 0; i < venueDS.entities.values.length; i++) {
            const ent = venueDS.entities.getById(venueDS.entities.values[i].id);
            if (ent.label) {
                ent.label.text = langIdx == 0 ? ent.properties['venue_name_en']._value : ent.properties['venue_name_zh']._value;
            }
        }
    });
}
                langBtn.addEventListener('click', changeLanguage)
            }
            // --- 1. 定義所有鐵路綫的站點順序與顏色 ---
const initDemo = async () => {
    addLanaguage()
    const queryUrl = encodeURI(`${venuePolygonApi}?service=WFS&version=2.0.0&request=GetFeature&outputFormat=application/json&srsname=EPSG:4326&count=5000`)
    const venueResponse = await fetch(queryUrl)
    const venueGeoJson = await venueResponse.json()
    
    const venueDataSource = new Cesium.GeoJsonDataSource('mtr_venue_polygon')
    await venueDataSource.load(venueGeoJson,{ stroke: new Cesium.Color(0.65, 0.18, 0.26, 0.5), fill: new Cesium.Color(0.65, 0.18, 0.26, 0.5), outline: false })

    // --- 1. 定義所有鐵路綫的站點順序與顏色 (加入高度偏移避免重疊) ---
// --- 1. 定義所有鐵路綫的站點順序與顏色 (包含新加入的線路) ---
    const mtrLines = [
        {
            name: "觀塘綫 (Kwun Tong Line)",
            color: "#00AB4E",
            offset: 5,
            order: ["Whampoa", "Ho Man Tin", "Yau Ma Tei", "Mong Kok", "Prince Edward", "Shek Kip Mei", "Kowloon Tong", "Lok Fu", "Wong Tai Sin", "Diamond Hill", "Choi Hung", "Kowloon Bay", "Ngau Tau Kok", "Kwun Tong", "Lam Tin", "Yau Tong", "Tiu Keng Leng"],
            positions: []
        },
        {
            name: "荃灣綫 (Tsuen Wan Line)",
            color: "#E2231A",
            offset: 10,
            order: ["Central", "Admiralty", "Tsim Sha Tsui", "Jordan", "Yau Ma Tei", "Mong Kok", "Prince Edward", "Sham Shui Po", "Cheung Sha Wan", "Lai Chi Kok", "Mei Foo", "Lai King", "Kwai Fong", "Kwai Hing", "Tai Wo Hau", "Tsuen Wan"],
            positions: []
        },
        {
            name: "港島綫 (Island Line)",
            color: "#0071CE",
            offset: 15,
            order: ["Kennedy Town", "HKU", "Sai Ying Pun", "Sheung Wan", "Central", "Admiralty", "Wan Chai", "Causeway Bay", "Tin Hau", "Fortress Hill", "North Point", "Quarry Bay", "Tai Koo", "Sai Wan Ho", "Shau Kei Wan", "Heng Fa Chuen", "Chai Wan"],
            positions: []
        },
        {
            name: "將軍澳綫 (Tseung Kwan O Line)",
            color: "#A35EB5",
            offset: 20,
            order: ["North Point", "Quarry Bay", "Yau Tong", "Tiu Keng Leng", "Tseung Kwan O", "Hang Hau", "Po Lam"],
            positions: []
        },
        {
            name: "將軍澳綫-康城支線",
            color: "#A35EB5",
            offset: 20,
            order: ["Tseung Kwan O", "LOHAS Park"], 
            positions: []
        },
        {
            name: "東涌綫 (Tung Chung Line)",
            color: "#F3A112",
            offset: 25,
            order: ["Hong Kong", "Kowloon", "Olympic", "Nam Cheong", "Lai King", "Tsing Yi", "Sunny Bay", "Tung Chung"],
            positions: []
        },
        {
            name: "迪士尼綫 (Disneyland Resort Line)",
            color: "#F582A8",
            offset: 30,
            order: ["Sunny Bay", "Disneyland Resort"],
            positions: []
        },
        // --- 新加入線路 ---
        {
            name: "機場快綫 (Airport Express)",
            color: "#007078", // 青綠色 (機場藍)
            offset: 35,
            order: ["Hong Kong", "Kowloon", "Tsing Yi", "Airport", "AsiaWorld-Expo"],
            positions: []
        },
        {
            name: "東鐵綫 (East Rail Line)",
            color: "#61B4E4", // 天藍色
            offset: 40,
            order: ["Admiralty", "Exhibition Centre", "Hung Hom", "Mong Kok East", "Kowloon Tong", "Tai Wai", "Sha Tin", "Fo Tan", "University", "Tai Po Market", "Tai Wo", "Fanling", "Sheung Shui", "Lo Wu"],
            positions: []
        },
        {
            name: "東鐵綫-落馬洲支線",
            color: "#61B4E4",
            offset: 40,
            order: ["Sheung Shui", "Lok Ma Chau"],
            positions: []
        },
        {
            name: "東鐵綫-馬場支線",
            color: "#61B4E4",
            offset: 40,
            order: ["火炭", "馬場", "大學"], // 使用中文匹配避免與主線衝突，或確保 API 名稱包含 Racecourse
            order: ["Fo Tan", "Racecourse", "University"],
            positions: []
        },
        {
            name: "屯馬綫 (Tuen Ma Line)",
            color: "#9A3820", // 棕色
            offset: 45,
            order: ["Wu Kai Sha", "Ma On Shan", "Heng On", "Tai Shui Hang", "Shek Mun", "City One", "Sha Tin Wai", "Che Kung Temple", "Tai Wai", "Hin Keng", "Diamond Hill", "Kai Tak", "Sung Wong Toi", "To Kwa Wan", "Ho Man Tin", "Hung Hom", "East Tsim Sha Tsui", "Austin", "Nam Cheong", "Mei Foo", "Tsuen Wan West", "Kam Sheung Road", "Yuen Long", "Long Ping", "Tin Shui Wai", "Siu Hong", "Tuen Mun"],
            positions: []
        },
        {
            name: "南港島綫 (South Island Line)",
            color: "#B5BD00", // 黃綠色
            offset: 50,
            order: ["Admiralty", "Ocean Park", "Wong Chuk Hang", "Lei Tung", "South Horizons"],
            positions: []
        }
    ];

    mtrLines.forEach(line => {
        line.positions = new Array(line.order.length).fill(null);
    });

    Object.values(venueDataSource.entities.values).forEach(entity => {
        const props = entity.properties;
        entity.name = props.venue_name_en;
        entity.polygon.arcType = Cesium.ArcType.GEODESIC;
        entity.polygon.extrudedHeight = props.venue_display_height;
        entity.polygon.height = props.venue_display_height_min;
        entity.polygon.closeTop = false;

        const polyPositions = entity.polygon.hierarchy.getValue(Cesium.JulianDate.now()).positions;
        const center = Cesium.BoundingSphere.fromPoints(polyPositions).center;
        const cartographic = Cesium.Cartographic.fromCartesian(center);
        const baseHeight = parseFloat(props.venue_display_height?._value || 50);

        // 標籤固定在最高處
        entity.position = Cesium.Cartesian3.fromRadians(cartographic.longitude, cartographic.latitude, baseHeight + 40);

        entity.label = {
            text: langIdx == 0 ? props.venue_name_en._value : props.venue_name_zh._value,
            font: 'bold 14px sans-serif',
            fillColor: Cesium.Color.WHITE,
            outlineColor: Cesium.Color.BLACK,
            outlineWidth: 4,
            style: Cesium.LabelStyle.FILL_AND_OUTLINE,
            verticalOrigin: Cesium.VerticalOrigin.BOTTOM,
            distanceDisplayCondition: new Cesium.DistanceDisplayCondition(0, 15000),
            disableDepthTestDistance: Number.POSITIVE_INFINITY
        };

        const venueNameEn = props.venue_name_en._value;
        mtrLines.forEach(line => {
            line.order.forEach((targetName, index) => {
                // 使用模糊匹配，並確保 "HKU" 等縮寫能被正確識別
                if (venueNameEn.toLowerCase().includes(targetName.toLowerCase())) {
                    // 根據每條線的 offset 設定不同的高度，實現立體交匯
                    line.positions[index] = Cesium.Cartesian3.fromRadians(cartographic.longitude, cartographic.latitude, baseHeight + line.offset);
                }
            });
        });
    });

    // --- 繪製線路 ---
    mtrLines.forEach(line => {
        const validPositions = line.positions.filter(p => p !== null);
        if (validPositions.length > 1) {
            viewer.entities.add({
                name: line.name,
                polyline: {
                    positions: validPositions,
                    width: 8,
                    material: new Cesium.PolylineGlowMaterialProperty({
                        glowPower: 0.2,
                        color: Cesium.Color.fromCssColorString(line.color)
                    }),
                    depthFailMaterial: new Cesium.PolylineGlowMaterialProperty({
                        glowPower: 0.2,
                        color: Cesium.Color.fromCssColorString(line.color).withAlpha(0.5)
                    }),
                    clampToGround: false
                }
            });
        }
    });

    viewer.dataSources.add(venueDataSource);
    viewer.flyTo(venueDataSource, {duration: 2});
};
            await initDemo()