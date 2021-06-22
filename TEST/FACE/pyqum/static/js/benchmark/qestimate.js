



$(document).ready(function(){
    // $('div.qestimatecontent').show();
    console.log( "QESTIMATE JS" );
});


let gAxisIndex = [];
let gValueIndex = [];

function isListChange(){}

function get_selectInfo(){

    $.ajaxSettings.async = false;

    let isAxisChange = false
    let isValueChange = false
    
    let axisIndex=[]
    let valueIndex=[]


    let indexData = {
        axisIndex:{
            isChange:isAxisChange,
            data:axisIndex},
        valueIndex:{
            isChange:isValueChange,
            data:valueIndex},
      }
    console.log( indexData );
    // $.ajax({
    //     dataType: "json",
    //     url: "/benchmark/get_parametersID",
    //     async: false, 
    //     success: function(htmlIDs) {


    //     }
    // });
    $.getJSON( '/benchmark/get_parametersID', 
    {}, 
        function (htmlIDs) {
            axisIndex = [4];
            valueIndex = new Array(htmlIDs.length);

            // First time
            if (gAxisIndex.length == 0){ gAxisIndex = [4]; }
            if (gValueIndex.length == 0){ gValueIndex = new Array(htmlIDs.length); }

            for ( i in htmlIDs) {
                if ( htmlIDs[i] != "Frequency" ){
                    valueIndex[i] = document.getElementById("select-"+htmlIDs[i]).selectedIndex;
                    console.log(" test" + valueIndex +" add ", valueIndex[i]  );

                    if ( valueIndex[i]!= gValueIndex[i] ){
                        isValueChange=true;
                        gValueIndex[i] = valueIndex[i];
                    }
                    let axisDimension = axisIndex.length;
                    if ( document.getElementById("check-"+htmlIDs[i]).checked && axisIndex.length<2 )
                    {
                        console.log(htmlIDs[i] +" is checked ");
                        axisIndex[axisDimension] = Number(i) ;
                        if ( Number(i)!=gAxisIndex[axisDimension] ){
                            isAxisChange=true;
                            gAxisIndex[axisDimension] = axisIndex[axisDimension];
                        }
                    }
                }else{
                    valueIndex[i]=0;
                }
            }
            indexData.axisIndex.isChange = isAxisChange;
            indexData.axisIndex.data = axisIndex;

            indexData.valueIndex.isChange = isValueChange;
            indexData.valueIndex.data = valueIndex;


    });
    console.log( indexData );
    return indexData
}



function plot1D ( data, axisKeys, plotId ){
    console.log("Plotting 1D");
    let traceNumber = axisKeys.y.length;
    let tracies = new Array(traceNumber);
    let ix;
    for (let i = 0; i < traceNumber; i++){
        if ( axisKeys.x.length != 1 ){
            ix = i
        }else{
            ix = 0
        }
        tracies[i] = {
        x: data[axisKeys.x[ix]],
        y: data[axisKeys.y[i]],
        name: axisKeys.y[i],
        mode: 'markers',
        type: 'scatter'
        };
    }


    Plotly.newPlot(plotId, tracies, {showSendToCloud: true});
}

function plot2D( data, axisKeys, plotId ) {
    console.log("Plotting 2D");
    console.log( "x length: " +data[axisKeys.x].length );

    // Frame assembly:
    var trace = {
        z: data[axisKeys.z], 
        x: data[axisKeys.x], 
        y: data[axisKeys.y], 
        zsmooth: 'best',
        mode: 'lines', 
        type: 'heatmap',
        width: 2.5
    };
    
    //console.log("1st z-trace: " + trace.z[0][0]);

    // Plotting the Chart using assembled TRACE:
    var Trace = [trace]
    Plotly.newPlot(plotId, Trace, {showSendToCloud: true});
};


// assemble 2D-data based on c-parameters picked
$(function () {
    $('#qFactor-plot-button').on('click', function () {

        $.ajaxSettings.async = false;
        let htmlIDs=[];
        $.getJSON( '/benchmark/get_parametersID', 
        {}, 
            function (id) {
                htmlIDs = [...id];
        });

        let indexData = get_selectInfo();

        if (gAxisIndex.length<=2 )
        {

            if ( indexData.axisIndex.isChange ){
                console.log( "2D plot" );
                console.log( indexData );
                $.getJSON( '/benchmark/qestimate/getJson_qestimate_plot',
                {   indexData: JSON.stringify(indexData),}, 
                    function (data) {
                    console.log( data );
                    let axisKeys = {
                        x: "Frequency",
                        y: htmlIDs[indexData.axisIndex.data[1]],
                        z: "Data_point",
                    }
                    console.log( data );

                    plot2D(data, axisKeys, "qFactor-plot-rawOverview2D");
                });
            }
            let indexData1D = JSON.parse(JSON.stringify(indexData));
            console.log(  "1D plot" );
            console.log(  indexData1D );
            indexData1D.axisIndex.data = [4];
            $.getJSON( '/benchmark/qestimate/getJson_qestimate_plot',
            {   indexData: JSON.stringify(indexData1D),}, 
                function (data) {
                console.log( data );
                let axisKeys = {
                    x: ["Frequency"],
                    y: ["Data_point","Fitted_curve"],
                }
                console.log( data.Fitted_curve );

                plot1D(data, axisKeys, "qFactor-plot-fittingResult");
            });

            
        }else{
            console.log( "Too many axis." );
        }
        

        $.ajaxSettings.async = true;

    });


    // Analysis data and plot
    $('#qFactor-fit-button').on('click', function () {

        $.ajaxSettings.async = false;
        let htmlIDs=[];
        $.getJSON( '/benchmark/get_parametersID', 
        {}, 
            function (id) {
                htmlIDs = [...id];
        });

        let fittingRangeFrom = document.getElementById("qFactor-fittingRange-from").value
        let fittingRangeTo = document.getElementById("qFactor-fittingRange-to").value
        let indexData = get_selectInfo();
        console.log( "fit from " + fittingRangeFrom + " to ",  fittingRangeTo);
        $.getJSON( '/benchmark/qestimate/getJson_qestimate_fitResult',{  
            fittingRangeFrom:fittingRangeFrom, fittingRangeTo:fittingRangeTo  
        }, function (data) {
            console.log( Object.keys(data) );
            console.log( data );
            
            let axisKeys_fitCurve = {
                x: htmlIDs[indexData.axisIndex.data[0]],
                y: htmlIDs[indexData.axisIndex.data[1]],
                z: "amplitude",
            }
            //plot2D( data, axisKeys_fitCurve, "qFactor-plot-fitOverview2D");
            let axisKeys_fitResult = {
                x: [htmlIDs[indexData.axisIndex.data[1]]],
                y: ["Qc_dia_corr", "Qi_dia_corr", "Ql", "fr"],
            }
            plot1D( data, axisKeys_fitResult, "qFactor-plot-fittingParameters");

        });



        $.ajaxSettings.async = true;
    });

    // saving exported mat-data to client's PC:
    $('#qFactor-save-button').on('click', function () {
        console.log("SAVING MAT FILE");
        $.ajaxSettings.async = false;

        let user = "";
        $.getJSON( '/benchmark/get_user', 
        {}, 
            function (name) {
                user = name;
        });
        // in order to trigger href send-file request: (PENDING: FIND OUT THE WEIRD LOGIC BEHIND THIS NECCESITY)
        console.log("STATUS download");
        $.ajax({
            url: 'http://qum.phys.sinica.edu.tw:5301/mach/uploads/ANALYSIS/resonator_fit[' + user + '].mat',
            method: 'GET',
            xhrFields: {
                responseType: 'blob'
            },
            success: function (data) {
                console.log("USER HAS DOWNLOADED resonator_fit from " + String(window.URL));
                var a = document.createElement('a');
                var url = window.URL.createObjectURL(data);
                a.href = url;
                a.download = 'resonator_fit.mat';
                document.body.append(a);
                a.click();
                a.remove();
                window.URL.revokeObjectURL(url);
            }
        });
        $.ajaxSettings.async = true;

        return false;
    });

    // Plot 1D raw data and fitting curve
    $('#qqFactor-plotFittedCurve-button').on('click', function () {

        $.ajaxSettings.async = true;

        $.getJSON( '/benchmark/get_parametersID', 
        {}, 
            function (id) {
                htmlIDs = [...id];
        });

        let indexData = get_selectInfo();
        let indexData1D = JSON.parse(JSON.stringify(indexData));
        indexData1D.axisIndex.data = [4];

        $.getJSON( '/benchmark/qestimate/get_qestimate_plot_fitCurve',{  
            indexData: JSON.stringify(indexData1D)    
        }, function (data) {


            console.log( data )
        });

        $.getJSON( '/benchmark/qestimate/plot',
        {   indexData: JSON.stringify(indexData1D),}, 
            function (data) {
            console.log( data );
            let axisKeys = {
                x: [htmlIDs[indexData.axisIndex.data[0]]],
                y: ["amplitude"],
            }
            console.log( axisKeys );

            plot1D(data, axisKeys, "qFactor-plot-fittingResult");
        });

        $.ajaxSettings.async = false;
    });
    //Just for test
    $('#qFactor-test-button').on('click', function () {


        $.getJSON( '/benchmark/test',{  
            
        }, function (data) {
            console.log( data )
        });

    });
    // Test new plot
    $('#qFactor-plottest-button').on('click', function () {
        console.log( "2D plot" );
        $.ajaxSettings.async = false;
        let htmlIDs=[];
        $.getJSON( '/benchmark/get_parametersID', 
        {}, 
            function (id) {
                htmlIDs = [...id];
        });

        let indexData = get_selectInfo();

        if (gAxisIndex.length<=2 )
        {

            console.log( "2D plot" );
            console.log( indexData );
            $.getJSON( '/benchmark/qestimate/getJson_2Dplot_test',
            {   indexData: JSON.stringify(indexData),}, 
                function (data) {
                console.log( data );
                let axisKeys = {
                    x: "Data_point.frequency",
                    y: htmlIDs[indexData.axisIndex.data[1]],
                    z: "Data_point",
                }
                console.log( data );

                plot2D(data, axisKeys, "qFactor-plot-rawOverview2D");
            });
            let indexData1D = JSON.parse(JSON.stringify(indexData));
            console.log(  "1D plot" );
            console.log(  indexData1D );
            $.getJSON( '/benchmark/qestimate/getJson_1Dplot_test',
            {   indexData: JSON.stringify(indexData1D),}, 
                function (data) {
                console.log( data );
                let axisKeys = {
                    x: ["Data_point.frequency","Fitted_curve.frequency"],
                    y: ["Data_point.amplitude","Fitted_curve.amplitude"],
                }
                console.log( data.Fitted_curve );

                plot1D(data, axisKeys, "qFactor-plot-fittingResult");
            });

            
        }else{
            console.log( "Too many axis." );
        }
        

        $.ajaxSettings.async = true;

    });
    //Test fit data
    $('#qFactor-fittest-button').on('click', function () {


        $.ajaxSettings.async = false;
        let htmlIDs=[];
        $.getJSON( '/benchmark/get_parametersID', 
        {}, 
            function (id) {
                htmlIDs = [...id];
        });

        let indexData = get_selectInfo();

        console.log( "Fit plot" );
        console.log( indexData );

        let fittingRangeFrom = document.getElementById("qFactor-fittingRange-from").value
        let fittingRangeTo = document.getElementById("qFactor-fittingRange-to").value
        console.log( "fit from " + fittingRangeFrom + " to ",  fittingRangeTo);
        $.getJSON( '/benchmark/qestimate/getJson_qestimate_fitResult',{  
            fittingRangeFrom:fittingRangeFrom, fittingRangeTo:fittingRangeTo  
        }, function (data) {

            let axisKeys_fitResult = {
                x: [htmlIDs[indexData.axisIndex.data[1]]],
                y: ["Qc_dia_corr", "Qi_dia_corr", "Ql", "fr"],
            }
            plot1D( data, axisKeys_fitResult, "qFactor-plot-fittingParameters");

            

        $.ajaxSettings.async = true;
        });
    });

});

