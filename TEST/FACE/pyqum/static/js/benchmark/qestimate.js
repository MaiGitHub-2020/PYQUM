



$(document).ready(function(){
    // $('div.qestimatecontent').show();
    console.log( "QESTIMATE JS" );
    render_QEstimation ();
});


let gAxisIndex = [];
let gValueIndex = [];

function get_htmlInfo_python(){
    let htmlInfo;
    $.getJSON( '/benchmark/get_parametersID', 
    {},
        function (data) {
            htmlInfo = data;
    });
    return htmlInfo
}

function get_selectInfo(){

    $.ajaxSettings.async = false;


    // $.ajax({
    //     dataType: "json",
    //     url: "/benchmark/get_parametersID",
    //     async: false, 
    //     success: function(htmlIDs) {
    //     }
    // });
    let htmlInfo = get_htmlInfo_python();
    let axisIndex=new Array(1);
    let valueIndex=new Array(htmlInfo.length);
    let analysisIndex = {};

    
    console.log( "htmlInfo " );
    console.log( htmlInfo.length );
    // Get select parameter index
    for (let i=0; i<htmlInfo.length; i++ ) {
        htmlName = htmlInfo[i]["name"];
        varLength = htmlInfo[i]["length"];
        structurePosition = htmlInfo[i]["structurePosition"]
        if ( varLength == 1 ){ valueIndex[i]=0 }
        else{

            if ( document.getElementById("plot_type-"+htmlName).value == "y_value" )
            {
                console.log(htmlName +" for y-axis ");
                axisIndex[axisIndex.length] = structurePosition ;
                valueIndex[i]=document.getElementById("select_value-"+htmlName).selectedIndex;
                
            }
            if( document.getElementById("plot_type-"+htmlName).value == "x_value" ){
                console.log(htmlName +" for x-axis ");
                axisIndex[0] = structurePosition ;
                valueIndex[i]=0;

            }
            if( document.getElementById("plot_type-"+htmlName).value == "single_value" ){
                console.log(htmlName +" select single value ");
                valueIndex[i]=document.getElementById("select_value-"+htmlName).selectedIndex;

            }
            
        }



    }
    analysisIndex["valueIndex"] = valueIndex;
    analysisIndex["axisIndex"] = axisIndex;
    console.log( "Selection " );
    console.log( analysisIndex );
    $.ajaxSettings.async = true;

    return analysisIndex
}



function plot1D ( data, axisKeys, plotId ){
    console.log("Plotting 1D");
    let traceNumber = axisKeys.y.length;
    console.log(axisKeys.x[0]);

    let tracies = new Array(traceNumber);
    let ix;
    for (let i = 0; i < traceNumber; i++){
        if ( axisKeys.x.length != 1 ){
            ix = i
        }else{
            ix = 0
        }

        if ( axisKeys.yErr.length == 0 || axisKeys.yErr[i]=="" ){
            yErr = {
                type: 'data',
                array: [],
                visible: false
              }
        }else{
            yErr = {
                type: 'data',
                array: data[axisKeys.yErr[i]],
                visible: true
              }
        }
        tracies[i] = {
        x: data[axisKeys.x[ix]],
        y: data[axisKeys.y[i]],
        error_y: yErr,
        name: axisKeys.y[i],
        mode: 'markers',
        type: 'scatter'
        };
    }

    Plotly.newPlot(plotId, tracies, {showSendToCloud: true});
}

function plot2D( data, axisKeys, plotId ) {
    console.log("Plotting 2D");
    console.log( "x axis: " +axisKeys.x );

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

// Render Qestimation
function render_QEstimation ()
{

    $.ajaxSettings.async = false;

    let measureParameters = document.getElementById("qFactor-parameters");



    let htmlInfo = [];
    $.getJSON( '/benchmark/get_parametersID', 
    {},
        function (data) {
            htmlInfo = data;
    });
    console.log( htmlInfo );
    for(i = 0; i < htmlInfo.length; i++) {
        let DOM_parameterSetting = document.createElement("div");
        DOM_parameterSetting.setAttribute("class", "measurePara");
        measureParameters.appendChild(DOM_parameterSetting);


        let parameterName = htmlInfo[i]["name"]
        console.log(i, parameterName);
        let DOM_parameterName = document.createElement("label");
        DOM_parameterName.innerHTML = parameterName;
        DOM_parameterName.setAttribute("class", "measureParaSelect");

        DOM_parameterSetting.appendChild(DOM_parameterName);
        // Create parameters information and plot selection
        if (htmlInfo[i]["length"] == 1) // The parameter only have one value
        {
            let DOM_parameterCOrder = document.createElement("p");
            DOM_parameterCOrder.innerHTML = htmlInfo[i]["c_order"];
            DOM_parameterCOrder.setAttribute("class", "measureCOrder");

            DOM_parameterSetting.appendChild(DOM_parameterCOrder);

        }
        else{ // The parameter number > 1
            let DOM_parameterPlotTypeSelector = document.createElement("select");
            DOM_parameterPlotTypeSelector.id = "plot_type-"+parameterName;
            DOM_parameterPlotTypeSelector.setAttribute("class", "measureParaSelect");
            DOM_parameterSetting.appendChild(DOM_parameterPlotTypeSelector);

            let plotType = ["single value","x axis - value","y axis - value","y axis - count"];
            let plotTypeValue = ["single_value","x_value","y_value","y_count"];

            for( ipt=0; ipt<plotType.length; ipt++)
            {
                let DOM_parameterPlotType = document.createElement("option");
                DOM_parameterPlotType.innerHTML = plotType[ipt];
                DOM_parameterPlotType.setAttribute("value", plotTypeValue[ipt]);
                DOM_parameterPlotTypeSelector.appendChild(DOM_parameterPlotType);
            }



            if ( htmlInfo[i]["length"]<50 ){
                let DOM_parameterValueSelector = document.createElement("select");
                DOM_parameterValueSelector.id = "select_value-"+parameterName;
                DOM_parameterValueSelector.setAttribute("class", "measureParaSelect");
                DOM_parameterSetting.appendChild(DOM_parameterValueSelector);
                let parameterValue;
                console.log(parameterName, " Selector ");

                $.getJSON( '/benchmark/get_parameterValue',
                {   parameterKey: parameterName,},
                    function (data) {
                    parameterValue=data;
                });
                for ( iv=0; iv<parameterValue.length; iv++)
                {
                    let DOM_parameterValue = document.createElement("option");
                    DOM_parameterValue.innerHTML = parameterValue[iv];
                    
                    DOM_parameterValueSelector.appendChild(DOM_parameterValue);
                }
            }else{
                let DOM_parameterValueInput = document.createElement("input");
                DOM_parameterValueInput.setAttribute("class", "measureParaSelect");
                DOM_parameterSetting.appendChild(DOM_parameterValueInput);

            }


        }

    }

    $.ajaxSettings.async = true;


}
$(function () {

    // saving exported mat-data to client's PC:
    $('#qFactor-Download-button').on('click', function () {
        console.log("SAVING CSV FILE");
    
        // in order to trigger href send-file request: (PENDING: FIND OUT THE WEIRD LOGIC BEHIND THIS NECCESITY)
        //$.getJSON(mssnencrpytonian() + '/mssn/char/' + frespcryption + '/access', { wmoment: wmoment }, function (data) {});
    
        $.getJSON( '/benchmark/qestimate/exportMat_fitPara', {
            //ifreq: $('select.char.fresp.parameter[name="c-freq"]').val()
        }, function (data) {
            console.log("STATUS: " + data.status + ", PORT: " + data.qumport);
            $.ajax({
                url: 'http://qum.phys.sinica.edu.tw:' + data.qumport + '/mach/uploads/ANALYSIS/QEstimation[' + data.user_name + '].mat',
                method: 'GET',
                xhrFields: {
                    responseType: 'blob'
                },
                success: function (data) {
                    console.log("USER HAS DOWNLOADED QEstimation DATA from " + String(window.URL));
                    var a = document.createElement('a');
                    var url = window.URL.createObjectURL(data);
                    a.href = url;
                    a.download = 'QEstimation.mat';
                    document.body.append(a);
                    a.click();
                    a.remove();
                    window.URL.revokeObjectURL(url);
                    //$('#qFactor-Download-button').hide();
                }
            });
        });
        return false;
    });


    //Just for test
    $('#qFactor-test-button').on('click', function () {


        $.getJSON( '/benchmark/test',{  
            
        }, function (data) {
            console.log( data )
        });

    });
    // plot
    $('#qFactor-plot-button').on('click', function () {
        let plotID_2D = "qFactor-plot2D-rawOverview";
        let plotID_1D_ampPhase = "qFactor-plot1D-ampPhase";
        let plotID_1D_IQ = "qFactor-plot1D-IQ";
        console.log( "plot!!" );
        $.ajaxSettings.async = false;
        let htmlInfo=get_htmlInfo_python();
        let analysisIndex = get_selectInfo();
        if ( analysisIndex.axisIndex.length == 2 ){
            $.getJSON( '/benchmark/qestimate/getJson_plot',
            {   analysisIndex: JSON.stringify(analysisIndex), plotType: JSON.stringify("2D_amp"), },
                function (data) {
                console.log( "2D plot" );
                console.log( data );
                let axisKeys = {
                    x: htmlInfo[analysisIndex.axisIndex[0]]["name"],
                    y: htmlInfo[analysisIndex.axisIndex[1]]["name"],
                    z: "amplitude",
                }
                console.log( data );
                
                document.getElementById(plotID_2D).style.display = "block";
                plot2D(data, axisKeys, plotID_2D);
            });
        }else{
            document.getElementById(plotID_2D).style.display = "none";
        }


        $.getJSON( '/benchmark/qestimate/getJson_plot',
        {   analysisIndex: JSON.stringify(analysisIndex), plotType: JSON.stringify("1D_amp"), },
            function (data) {
            console.log( "1D amp plot" );
            console.log( data );
            let axisKeys = {
                x: ["Data_point_frequency","Fitted_curve_frequency","Fitted_baseline_frequency","Corr_Data_point_frequency"],
                y: ["Data_point_amplitude","Fitted_curve_amplitude","Fitted_baseline_amplitude","Corr_Data_point_amplitude"],
                yErr: [],
            }
            //console.log( data.Fitted_curve_amplitude );

            plot1D(data, axisKeys, plotID_1D_ampPhase);
        });

        $.getJSON( '/benchmark/qestimate/getJson_plot',
        {   analysisIndex: JSON.stringify(analysisIndex), plotType: JSON.stringify("1D_IQ"), },
            function (data) {
            console.log( "1D IQ plot" );
            console.log( data );
            let axisKeys = {
                x: ["Data_point_I","Fitted_curve_I","Fitted_baseline_I","Corr_Data_point_I"],
                y: ["Data_point_Q","Fitted_curve_Q","Fitted_baseline_Q","Corr_Data_point_Q"],
                yErr: [],
            }
            //console.log( data.Fitted_curve_amplitude );

            plot1D(data, axisKeys, plotID_1D_IQ);
        });

        $.ajaxSettings.async = true;

    });
    //Test fit data
    $('#qFactor-fit-button').on('click', function () {

        $.ajaxSettings.async = false;
        let htmlInfo=get_htmlInfo_python();
        let analysisIndex = get_selectInfo();

        console.log( "Fit plot" );
        console.log( analysisIndex );

        let rangeFrom = document.getElementById("qFactor-fit-range-from").value;
        let rangeTo = document.getElementById("qFactor-fit-range-to").value;
        let baseline_correction = document.getElementById("qFactor-fit-baseline-correct").checked;
        let baseline_smoothness = document.getElementById("qFactor-fit-baseline-smoothness").value;
        let baseline_asymmetry = document.getElementById("qFactor-fit-baseline-asymmetry").value;
        let gain = document.getElementById("qFactor-fit-gain").value;

        let fitParameters = {
            range: {
                from: rangeFrom,
                to: rangeTo
            },
            baseline:{
                correction: baseline_correction,
                smoothness: baseline_smoothness,
                asymmetry: baseline_asymmetry,
            },
            gain:gain,
            
        }
        console.log(fitParameters);


        // Plot fit parameters
        $.getJSON( '/benchmark/qestimate/getJson_fitParaPlot',{  
            fitParameters: JSON.stringify(fitParameters),
            analysisIndex: JSON.stringify(analysisIndex), 
        }, function (data) {
            let xAxisKey = "Single_plot";
            if (analysisIndex.axisIndex.length == 2) { xAxisKey = htmlInfo[analysisIndex.axisIndex[0]]["name"] }
            //if ( xAxisKey == "Power" ) { xAxisKey = "power_corr" }

            let axisKeys_fitResult = {
                x: [xAxisKey],
                y: ["Qc_dia_corr", "Qi_dia_corr", "Ql", "fr", "single_photon_limit", "photons_in_resonator"],
                yErr: ["absQc_err", "Qi_dia_corr_err", "Ql_err", "fr_err", "", ""],
            }
            plot1D( data, axisKeys_fitResult, "qFactor-plot-fittingParameters");

        });


        // Renew 1D plot
        // $.getJSON( '/benchmark/qestimate/getJson_plot',
        // {   analysisIndex: JSON.stringify(analysisIndex), plotDimension: JSON.stringify(1)}, 
        //     function (data) {
        //     console.log( "1D plot" );
        //     console.log( data );
        //     let axisKeys = {
        //         x: ["Data_point_frequency","Fitted_curve_frequency","Fitted_baseline_frequency","Corr_Data_point_frequency"],
        //         y: ["Data_point_amplitude","Fitted_curve_amplitude","Fitted_baseline_amplitude","Corr_Data_point_amplitude"],
        //         yErr: [],
        //     }
        //     //console.log( data.Fitted_curve_amplitude );

        //     plot1D(data, axisKeys, "qFactor-plot-fittingResult");
        // });
        $.ajaxSettings.async = true;

    });

});

