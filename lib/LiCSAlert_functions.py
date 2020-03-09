# -*- coding: utf-8 -*-
"""
A selection of functions used by LiCSAlert

@author: Matthew Gaddes
"""
#%%

def LiCSAlert(sources, time_values, ifgs_baseline, ifgs_monitoring = None, t_recalculate = 10, verbose=False):
    """ Main LiCSAlert algorithm for a daisy-chain timeseries of interferograms.  
    
    Inputs:
        sources | r2 array | sources (from ICASAR) as row vectors, as per ICA
        ifgs_baseline | r2 array | ifgs used in training stage as row vectors
        time_values | r1 array | time values for each point in the time series, commonly (12,24,36) for Sentinel-1 data
        t_recalculate | int | rolling lines of best fit are recalcaluted every X times (nb done in number of data points, not time between them)
        verbose | boolean | if True, various information is printed to screen.  
        
    Outputs
        sources_tcs_monitor | list of dicts | list, with item for each time course.  Each dictionary contains the cumualtive time course, the 
                                                cumulative time courses gradient, the rolling lines of best fit, the standard deviation of the 
                                                line-to-point distances for the baseline data, and the line-to-point distances.  
        residual_tcs_monitor | list of dicts | As per above, but only for the cumulative residual (i.e. list is length 1)
    History:
        2019/12/XX | MEG |  Written from existing script.  
        2020/02/16 | MEG |  Update to work with no monitoring interferograms
    """
    from LiCSAlert_functions import bss_components_inversion, residual_for_pixels, tcs_baseline, tcs_monitoring  
    import numpy as np
    
    # Begin
    
    n_times_baseline = ifgs_baseline.shape[0]
    if ifgs_monitoring is None:
        ifgs_all = np.copy(ifgs_baseline)                                                                # if there are no monitoring ifgs, ifgs_all is just the set of baseline ifgs
        n_times_monitoring = 0                                                                           # there are no monitoring ifgs
    else:
        ifgs_all = np.vstack((ifgs_baseline, ifgs_monitoring))                                           # ifgs are row vectors, so stack vertically
        n_times_monitoring = ifgs_monitoring.shape[0]
    print(f"LiCSAlert for 'volcano' with {n_times_baseline} baseline interferograms and {n_times_monitoring} monitoring interferogram(s).  ")    
        
    # 1: calculating time courses/distances etc for the baseline data
    tcs_c, _ = bss_components_inversion(sources, ifgs_baseline, cumulative=True)                         # compute cumulative time courses for baseline interferograms
    sources_tcs = tcs_baseline(tcs_c, time_values[:n_times_baseline], t_recalculate)                     # lines, gradients, etc for time courses 
    _, residual_cb = residual_for_pixels(sources, sources_tcs, ifgs_baseline)                            # get the cumulative residual for the baseline interferograms
    residual_tcs = tcs_baseline(residual_cb, time_values[:n_times_baseline], t_recalculate)              # lines, gradients. etc for residual 
    del tcs_c, residual_cb
    
    #2: Calculate time courses/distances etc for the monitoring data
    if ifgs_monitoring is not None:
        tcs_c, _ = bss_components_inversion(sources, ifgs_monitoring, cumulative=True)                      # compute cumulative time courses for monitoring interferograms
        sources_tcs_monitor = tcs_monitoring(tcs_c, sources_tcs, time_values)                               # update lines, gradients, etc for time courses 
    
        #3: and update the residual stuff                                                                            # which is handled slightly differently as must be recalcualted for baseline and monitoring data
        _, residual_c_bm = residual_for_pixels(sources, sources_tcs_monitor, ifgs_all)                               # get the cumulative residual for baseline and monitoring (hence _cb)    
        residual_tcs_monitor = tcs_monitoring(residual_c_bm, residual_tcs, time_values, residual=True)               # lines, gradients. etc for residual 
    


    if ifgs_monitoring is None:
        return sources_tcs, residual_tcs
    else:
        return sources_tcs_monitor, residual_tcs_monitor
    


#%%

def residual_for_pixels(sources, sources_tcs, ifgs, n_skip=None):
    """
    Given spatial sources and their time courses, reconstruct the entire time series and calcualte:
        - RMS of the residual between each reconstructed and real ifg
        - RMS of the cumulative residual between each reconstucted and real ifg
    N.b. if you only want to use some of the time courses (ie time course is 100 ifgs long, but only using the last 50 ifgs),
         this first n_skip ifgs can be set.  

    Inputs:
        sources | r2 array | sources as row vectors
        tcs | list of dicts | As per LiCSAlert, a list with an item for each sources, and each item is a dictionary of various itmes
        ifgs | r2 array | interferograms as row vectors
        n_skip | None or int | if an int, the first n_skip values of the timecourses will be skipped.  

    Outputs:
        residual_ts | r2 array | Column vector of the RMS residual between that ifg, and its reconstruction
        residual_cs | r2 array | Column vector of the RMS residual between an ifg and the cumulative residual (for each pixel)
                                 N.b. the point is that if we have a strong atmosphere, it then reverses in the next ifg
                                 so the cumulative for each pixel goes back to zero

    2019/01/XX | MEG | Written, in discussion with AH
    2019/12/06 | MEG | Comment and documentation
    2020/01/02 | MEG | Update to use new LiCSAlert list of dictionaries
    2020/02/06 | MEG | Fix bug as had forgotten to convert cumulative time courses to be incremental
    """

    import numpy as np

    def list_dict_to_r2(sources_tcs):
        """Conver the LiCSAlert list of dictionaries to a rank 2 array with time courses as column
        vectors.  """
        
        n_sources = len(sources_tcs)
        n_ifgs = sources_tcs[0]["cumulative_tc"].shape[0]                               # as many rows as time steps
        tcs_r2 = np.zeros((n_ifgs, n_sources))                                          # initiate
        for n_source, source_tc in enumerate(sources_tcs):                              # loop through each source
                tc_c = source_tc["cumulative_tc"]                                       # and copy the cumulative time course out
                tc = np.diff(np.vstack((np.array([0]), tc_c)), axis = 0)                # convert to incremental time course
                tcs_r2[:,n_source:n_source+1] = tc                                      # store as column vector
        return tcs_r2
                    

    (n_sources, n_pixs) = sources.shape                                         # number of sources and number of pixels
    tcs = list_dict_to_r2(sources_tcs)                                          # get the incremental time courses as a rank 2 array
    if n_skip is not None:                                                      # crop/remove the first ifgs
        tcs = tcs[n_skip:,]                                                        # usually the baseline ifgs when used with monitoring data
    
    data_model_residual = ifgs - (tcs @ sources)                                # residual for each pixel at each time
    data_model_residual_cs = np.cumsum(data_model_residual, axis = 0)           # summing the residual for each pixel cumulatively through time   
    residual_ts = np.zeros((data_model_residual.shape[0], 1))                                   # initiate, n_ifgs x 1 array
    residual_cs = np.zeros((data_model_residual.shape[0], 1))                                   # initiate, n_ifgs x 1 array
    for row_n in range(data_model_residual.shape[0]):                                           # loop through each ifg
        residual_ts[row_n, 0] = np.sqrt(np.sum(data_model_residual[row_n,:]**2)/n_pixs)         # RMS of residual for each ifg
        residual_cs[row_n, 0] = np.sqrt(np.sum(data_model_residual_cs[row_n,:]**2)/n_pixs)      # RMS of residual for cumulative
    
    return residual_ts, residual_cs

#%%

def tcs_baseline(tcs_c, time_values, t_recalculate):
    """
    Given cumulative time courses (tsc_c), the time values for each entry (time_values), and the recalculation time 
    (t_recalculate), create a list with a dictionary about each time course.  The dictionary contains the cumulative 
    time courses, their gradient, and the ditsances each point is from a line of best fit at that gradient, and the 
    lines of best fit, redrwwn every t_recalculate.  
    
    Inputs:
        tcs_c | rank2 array | Cumulative Time CourseS, as column vectors
        time_values  | r1 array | time values for each point in the time course.  for Sentinel-1, commonly (12,24,36 etc)
        t_recalculate | int | the number of ifgs used to calculate the rolling lines of best fit
    
    Outputs:
        sources_tcs | list of dicts | as per description.  
        
    History:
        2020/01/02 | MEG | Written
    """
    import numpy as np
    
    n_times, n_tcs = tcs_c.shape                                                                    # there will be as many time courses (tcs) as there are sources, which are rows
    sources_tcs = []                                                                           # each time course will be a list
    for n_tc in range(n_tcs):
        tc_dict = {}                                                                           # initialise
        # 1: add the cumulative time course
        tc_dict["cumulative_tc"] = tcs_c[:, n_tc:n_tc+1]                                       # keep cumulative time course as a column vector
        
        # 2: add the gradient 
        gradient, y_intercept = np.polyfit(time_values, tc_dict["cumulative_tc"], 1)            # gradients 1st, y intercept second        
        tc_dict["gradient"] = gradient[0]                                                       # add to dictionary
        
        # 3: Lines of best fit
        line_yvals = np.polyval((tc_dict["gradient"], y_intercept), time_values)                # line of best fit, using the calcaulted y value
        lines_yvals = np.nan * np.ones((n_times, n_times))                                      # initiate as nans
        for time_step in range(n_times):                                                        # loop through each time step, to calculate it
            start_time = time_step - (t_recalculate-1)
            if start_time < 0:                                                                  # can't have negative time
                start_time = 0
            lines_yvals[start_time:time_step+1, time_step] = line_yvals[start_time:time_step+1]              # copy the y values for that little bit of line
        tc_dict["lines"] = lines_yvals                                                          # add to dictionary
        
        # 4: line to point distances (which are stored in the dict in terms of how many sigmas they are)
        line_point_distances = tc_dict["cumulative_tc"] - line_yvals[:,np.newaxis]
        tc_dict["sigma"] = np.std(line_point_distances)
        tc_dict["distances"] = np.abs(line_point_distances / tc_dict["sigma"])                  # ie the number of standard deviations a point is from the line of best fit
        
        # 5: Record the t_recalculate parameter
        tc_dict["t_recalculate"] = t_recalculate
        
        sources_tcs.append(tc_dict)                                                            # append to list, where each item is a time_course dictionary
    return sources_tcs
    
#%%    
    
def tcs_monitoring(tcs_c, sources_tcs, time_values, residual=False):
    """
    Given an extension to a time series (i.e. not in monitoring mode) and given the time courses for the baseline
    data (sources_tcs), create a new list of dicts for the complete data (i.e. rolling lines of best fit, line to point
    distances).  
    
    Inputs:
        tcs_cs | rank 2 array | time courses as column vectors
        sources_tcs | list of dicts | 
        time_values  | r1 array | time values for each point in the time course.  for Sentinel-1, commonly (12,24,36 etc)
        
    Outputs:
        sources_tcs | list of dicts | as per description.  
        
    History:
        2020/01/02 | MEG | Written
    """
    import numpy as np
    import copy                                                                                   # needed for the deep copy of the list of dictionaries
    
    # 1: Small initial steps
    sources_tcs_monitor = copy.deepcopy(sources_tcs)                                              # copy so that we can change without affecting version calcaulted only from baseline data
    t_recalculate = sources_tcs_monitor[0]["t_recalculate"]                                       # get the recalculation time used during the baseline stage
    n_times_baseline = sources_tcs_monitor[0]["cumulative_tc"].shape[0]
    n_times_tc = tcs_c.shape[0]                                                              # number of time steps is just the number of interferograms
    
    if residual:
        n_times_monitor = n_times_tc - n_times_baseline
    else:
        n_times_monitor = n_times_tc
    n_times_total = n_times_baseline + n_times_monitor       
    
    for source_n, source_tc in enumerate(sources_tcs_monitor):
        # 1: Update the cumulative time course 
        if residual is False:                                                                                   # residual timecourse doesn't start from 0, so don't need to add value to it
            tcs_c[:, source_n] += source_tc["cumulative_tc"][-1]                                                # add last value of cumulative tc, so that we continue from that value (and don't reset ot zero0)
            source_tc["cumulative_tc"] = np.vstack((source_tc["cumulative_tc"], tcs_c[:, source_n][:, np.newaxis]))        # extend the cumulative time course
        else:
            source_tc["cumulative_tc"] = tcs_c[:, source_n][:, np.newaxis]                                    # don't need to extend as have full time course
        
        # 2: Lines of best fit, and line to point distances
        source_tc["lines"] = np.pad(source_tc["lines"], [(0,n_times_monitor),(0,n_times_monitor)], "constant", constant_values=(np.nan))        # resize, keeping original values in top left corner
        source_tc["distances"] = np.pad(source_tc["distances"], [(0, n_times_monitor), (0,0)], "constant", constant_values=(0))                 # lengthen to incorporate the monitoring data
        for n_ifg in np.arange(n_times_baseline, n_times_total):                                                                                # loop through each monitoring ifg
            line_y_intercept = np.mean(source_tc["cumulative_tc"][n_ifg-t_recalculate: n_ifg]) - (source_tc["gradient"]*np.mean(time_values[n_ifg-t_recalculate: n_ifg]))                   # find the y-intercept of a the line 
            line_yvals = (time_values[n_ifg-t_recalculate: n_ifg+1] * source_tc["gradient"]) + line_y_intercept                                                                      # predict the y values given the gradient and y-intercept of the line, note that also predicting y value for next point
            source_tc["lines"][n_ifg-t_recalculate: n_ifg+1, n_ifg] = line_yvals
            source_tc["distances"][n_ifg,] = (np.abs(source_tc["cumulative_tc"][n_ifg,] - line_yvals[-1]))/source_tc["sigma"]      
    return sources_tcs_monitor
    
#%%

def LiCSAlert_figure(sources_tcs, residual, sources_downsampled, displacement_r2, n_baseline_end, time_values, 
                     time_value_end=None, out_folder=None, ifg_xpos_scaler = 15):
    """
    The main fucntion to draw the LiCSAlert figure.  
    
    Inputs:
        sorces_tcs | list of dicts | Each source is an item in the list and has its own dictionary, containing information such as the lines of best, the graident learned
                                     in the baseline stage, the lines-of-best-fit to points distances etc.  
        sources_downsampled | r2 array | sorces (recoverd by ICASAR) as row vectors.  N.b. must be the same size as the mask
        displacement_r2 | dict | contains ifgs as row vectors in "incremental" and their mask ("mask"), and also downsampled versions for faster figures
                                  Downsampled ones used in plotting!  
        mask | r2 array | to convert an ifg (or source) as a row vector into a rank 2 masked array
        
        n_baseline_end | int | number of ifgs at which we switch from baseline to monitoring
        time_values | r1 array | time values to end date of each ifg.  e.g. [12,24,36] etc.  
        time_value_end | int or None | if an int, axes are extended to this time value, even if it's larrger than the last value of time_values
        out_folder | None or string | If not None, output pngs are saved to this location and the matplotib figures closed
        ifg_xpos_scaler | int | To be positioned correctly in the x direction, the ifgs that are plotted on the upper row must not be taller
                                than the axis they lie within.  Increasing this value makes the ifgs smaller, and therefore fit.  
     
    Returns:
        figure
        
    History:
        2020/01/XX | MEG | Written
        2020/01/10 | MEG | update to add "upper_time_values"
        2020/02/16 | MEG | add ifg_xpos_scaler to make sure ifgs are plotted with the correct x value.  
        2020/03/08 | MEG | Change plotting of ifgs and sources to awlays be the downsampled ones.  
    
    """
    import numpy as np
    import matplotlib.pyplot as plt
    import matplotlib.gridspec as gridspec
    from matplotlib import ticker
    import matplotlib as mpl
    from matplotlib.ticker import MultipleLocator
    # MEG imports
    from small_plot_functions import col_to_ma, make_colormap 
    
    def calcualte_line_args(n_ifgs, t_recalculate):
        """Lines of best fit are calculated for eahc time step, but we don't want
        to plot them all (as they lie on top of each other, mostly).  
        Therefore, calcaulte the numbers of which to plot so that they don't overlap.  '
        """
        line_args = []    
        for k in range(n_ifgs):
            if k % t_recalculate == 0 and k != 0:                                   # pick which ones, but have to exclue the 0th one
                line_args.append(k-1)
            if k == (n_ifgs-1) and k not in line_args:                              # and always pick the last one
                line_args.append(k)
        return line_args
    

    def plot_ifgs(ifgs, pixel_mask, figure, gridspec_area, time_values, minorLocator, majorLocator, xlim):
        """ Plot all the ifgs (baseline and monitoring) within the grispec_area.  
        """

        # 1: Create a single wide axes for the inset axes to be plotted on
        ax_ifgs = plt.Subplot(figure, gridspec_area)                                       # a thin but wide axes for all the thumbnail ifgs along the top to go in
        fig1.add_subplot(ax_ifgs)                                                          # add to figure
        ax_ifgs.set_yticks([])                                                             # no y ticks
        ax_ifgs.set_ylim(bottom = 0, top = 1)
        ax_ifgs.set_xlim(left = 0, right = xlim)                                           # set x axis upper limit to be the number of acquisitions in the time series
        ax_ifgs.set_xticklabels([])
        ax_ifgs.xaxis.set_major_locator(majorLocator)                                      # Major and minor tick lables 
        ax_ifgs.xaxis.set_minor_locator(minorLocator)
        for ifg_n, source in enumerate(ifgs):                                                                                # ifgs are rows, loop through
            iax = ax_ifgs.inset_axes([time_values[ifg_n], 0., (xlim/ifg_xpos_scaler), 1.], transform=ax_ifgs.transData)      # [xpos, ypos, xwidth, ywidth], note the x_pos_scaler that reduces the size of the inset axes to make sure it remains in tehe right place
            iax.imshow(col_to_ma(source, pixel_mask), cmap = plt.get_cmap('coolwarm'))                                       # plot on the axes
            iax.set_xticks([])                                                                                               # images so get rid of x and y ticks (nb this is just for the inset axes)
            iax.set_yticks([])
            # print(time_values[ifg_n])                                                                       # for debugging
            # plt.pause(1)                                                                                    # "

    def colourbar_for_sources(icasar_sources):
        """ Creat a colourbar for the ICA sources that is centered on 0, and cropped so that each side is equal
        (i.e. if data lies in range [-1 10], will only go slightly blue, but up to max red, with grey at 0)
        """
        from small_plot_functions import remappedColorMap
        ics_min = np.min(icasar_sources)                                                       # 
        ics_max = np.max(icasar_sources)
        ic_colours = plt.get_cmap('coolwarm')
        cmap_mid = 1 - ics_max/(ics_max + abs(ics_min))                                     # get the ratio of the data that 0 lies at (eg if data is -15 to 5, ratio is 0.75)
        ic_colours_cent = remappedColorMap(ic_colours, start=0.0, midpoint=cmap_mid, stop=1, name='ic_colours_cent')                    # make the colours for plotting the ICs
        return ic_colours_cent
    
    def sigma_bar_plotter(ax_tc, xvals, yvals, sigma_cmap):
        """
        Add the bar plots onto an axes to show how many sigmas from the line each point is.  
        Inputs:
            ax_tcs | axes object | axes on which to plot
            xvals | x values of bars - usually time
            yvals | height of bars - the number of sigmas from the mean that point is
        """
        ax_tc2 = ax_tc.twinx()                                                       # instantiate a second axes that shares the same x-axis
        for point_n, xval in enumerate(xvals):                                       # loop along each bar
            ax_tc2.bar(xval, yvals[point_n], width=10, alpha = 0.3, color = sigma_cmap(yvals[point_n]/5))   # and plot in required colour
        ax_tc2.set_yticklabels([])                                                      # turn off y labels
        ax_tc2.set_ylim(top = 10)                                                       # set so in range 0 to 10

   
        
    # 0: Start, some definitions that shouldn't need changing
    #line_best_fit_alpha = 0.7
    dot_marker_size = 12
    majorLocator = MultipleLocator(96)                                                  # in days, good to be a multiple of 12 for Sentinel-1 data
    minorLocator = MultipleLocator(12)                                                  # as above
    if time_value_end is None:
        t_end = time_values[-1]                                                         # last time value - i.e. the right hand x value of all the axes
    else:
        t_end = time_value_end                                                          # or if it was provided, just use that value
    
    
    # 1 set some preliminary stuff
    t_recalculate = sources_tcs[0]["t_recalculate"]
    n_ics = len(sources_tcs)
    n_times = time_values.shape[0] 
    n_ifgs = displacement_r2["incremental"].shape[0]
    line_args= calcualte_line_args(n_times, t_recalculate)                      # which lines of best fit to plot
    c = mpl.colors.ColorConverter().to_rgb                                      
    cmap_discrete = make_colormap(  [c('black'), c('orange'), 0.33, c('orange'), c('yellow'), 0.66, c('yellow'), c('red')])     # custom colorbar for number of sigmas from line
    cmap_sources = colourbar_for_sources(sources_downsampled)
    figtitle = f'LiCSAlert figure with {n_ifgs-n_baseline_end} monitoring interferograms'

    # 2 Initiate the figure    
    fig1 = plt.figure(figsize=(14,8))
    fig1.canvas.set_window_title(figtitle)
    grid = gridspec.GridSpec((n_ics + 2), 11, wspace=0.3, hspace=0.1)                        # divide into 2 sections, 1/5 for ifgs and 4/5 for components

    # 3: Plot the ifgs along the top
    plot_ifgs(displacement_r2["incremental_downsampled"], displacement_r2["mask_downsampled"], fig1, grid[0,1:], time_values, minorLocator, majorLocator, t_end)

    # 4: Plot each source and its time course 
    try:
        baseline_monitor_change = np.mean([time_values[n_baseline_end-1], time_values[n_baseline_end]])                                     # Vertical line will be drawn at this time value to show that we switch from baseline to monitoring
    except:
        baseline_monitor_change = np.mean([time_values[n_baseline_end-1], time_values[n_baseline_end-1] + 12])                              # But the above won't work if there are no monitoring ifgs, so just guess next ifg will be after 12 days and draw line as if that were true (ie 6 days after last point)
    for row_n, source_tc in enumerate(sources_tcs):
        # plot the source as an image
        ax_source = plt.Subplot(fig1, grid[row_n+1,0])
        im = ax_source.imshow(col_to_ma(sources_downsampled[row_n], displacement_r2["mask_downsampled"]), cmap = cmap_sources, vmin = np.min(sources_downsampled), vmax = np.max(sources_downsampled))   
        ax_source.set_xticks([])
        ax_source.set_yticks([])
        ax_source.set_ylabel(f"IC {row_n+1}")
        fig1.add_subplot(ax_source)
        
        # plot the time courses for that IC, and the rolling lines of best fit
        ax_tc = plt.Subplot(fig1, grid[row_n+1,1:])
        ax_tc.scatter(time_values, source_tc["cumulative_tc"], c = source_tc["distances"], marker='o', s = dot_marker_size, cmap = cmap_discrete, vmin = 0, vmax = 5, )                        # 
        for line_arg in line_args:
            ax_tc.plot(time_values, source_tc["lines"][:,line_arg], c = 'k')
    
        # # tidy up some stuff on the axes
        ax_tc.axhline(y=0, color='k', alpha=0.3)  
        ax_tc.axvline(x = baseline_monitor_change, color='k', alpha=0.3)                          #line the splits between baseline and monitoring ifgs
        ax_tc.set_xlim(left = 0, right = t_end)
        ax_tc.set_xticklabels([])
        ax_tc.xaxis.set_major_locator(majorLocator)                                                 # Major and minor tick lables 
        ax_tc.xaxis.set_minor_locator(minorLocator)
        fig1.add_subplot(ax_tc)
        sigma_bar_plotter(ax_tc, time_values, source_tc["distances"], cmap_discrete)                # draw the bar graph showing sigma values
        ax_tc.yaxis.tick_right()                                                                    # has to be called after sigma_bar_plotter
                                                                

    # 5: Plot the residual
    ax_residual = plt.Subplot(fig1, grid[-1,1:])                                                                    # plot on the last row
    ax_residual.scatter(time_values, residual[0]["cumulative_tc"], marker='o', s = dot_marker_size, cmap = cmap_discrete, vmin = 0, vmax = 5, c = residual[0]["distances"])         # 
    for line_arg in line_args:                                                                                      # plot the rolling line of best fit
        ax_residual.plot(time_values, residual[0]["lines"][:,line_arg], c = 'k')    
    ax_residual.axhline(y=0, color='k', alpha=0.3)
    ax_residual.axvline(x = baseline_monitor_change, color='k', alpha=0.3)                          #line the splits between baseline and monitoring ifgs
    ax_residual.set_xlim(left = 0, right = t_end)                    # and finaly tidy up axis and labels etc.  
    ax_residual.yaxis.tick_right()
    ax_residual.yaxis.set_label_position("right")
    ax_residual.set_ylabel('RMS\nresidual')
    ax_residual.xaxis.set_major_locator(majorLocator)                             # Major and minor tick lables 
    ax_residual.xaxis.set_minor_locator(minorLocator)
    fig1.add_subplot(ax_residual)
    sigma_bar_plotter(ax_residual, time_values, residual[0]["distances"], cmap_discrete)                    # draw the bar graph showing sigma values
    ax_residual.yaxis.tick_right()                                                                        # has to be called after sigma_bar_plotter
    ax_residual.set_xlabel('Time (days)')
    
    ## 6: add the two colorbars
    cax = fig1.add_axes([0.12, 0.08, 0.005, 0.1])                                      # source strength
    ics_cbar = fig1.colorbar(im, cax=cax, orientation='vertical')
    tick_locator = ticker.MaxNLocator(nbins=4)
    ics_cbar.locator = tick_locator
    ics_cbar.update_ticks()
    ics_cbar.set_label('IC strength (rad)')
    ics_cbar.ax.yaxis.set_label_position('left')
    
    cax2 = fig1.add_axes([0.17, 0.08, 0.005, 0.1])                                            # number of sigmas from the mean
    norm = mpl.colors.Normalize(vmin=0, vmax=5)
    std_cbar = mpl.colorbar.ColorbarBase(cax2, cmap=cmap_discrete, norm=norm,orientation='vertical')
    tick_locator2 = ticker.MaxNLocator(nbins=5)
    std_cbar.locator = tick_locator2
    std_cbar.update_ticks()
    std_cbar.set_label(r'$\sigma$ from trend line')
    std_cbar.ax.yaxis.set_label_position('left')
    
    # 7: Possible save output
    if out_folder is not None:
        filename = "_".join(figtitle.split(" "))                                            # figtitle has spaces, but filename must use underscores instead.  
        fig1.savefig(f'{out_folder}/{filename}.png', bbox_inches='tight')
        plt.close(fig1)


#%%
        
        
def LiCSBAS_for_LiCSAlert(frame, downsampling = 1):
    """ Call this to either create a LiCSBAS timeseries from LiCSAR products, or to update one when new products become available.  
    
    Inputs:
        frame | string | The frame nameas defined by LiCSAR
        downsampling | int | >=1, sets the downsampling (mulitlooking in both range and azimuth?)
        
    Returns:
        All products described in the LiCSBAS documentation.  
        Of importance for use with LiCSAlert are:
            cum.h5
            
    History:
        2020/02/15 | MEG | Written
        
    """

    import os
    import sys
    
    sys.path.append("/home/matthew/university_work/03_automatic_detection_algorithm/07_LiCSBAS/LiCSBAS/bin")                  # location of LiCSBAS functions
    
    # Inputs args - probably a better way to change these (rather than hard-coding)    
    p11_unw_thre = 0.5
    p11_coh_thre = 0.1
    p12_loop_thre = 1.5                 # in rads
    
    #Rarely changed
    p13_inv_alg = "LS"              	# LS (default) or WLS
    p13_mem_size = 4000	                # default: 4000 (MB)
    p13_gamma = 0.0001              	# default: 0.0001
    p13_n_core = 1	                    # default: 1
    p13_n_unw_r_thre = 1	            # defualt: 1
    p13_keep_incfile = "n"	            # y/n. default: n

    GEOCmldir = f"GEOCml{downsampling}"
    TSdir = f"TS_GEOCmldir"
       
    # Convert format (LiCSBAS02)  NB: This will automatically skip files that have already been converted.  
    os.system(f"LiCSBAS02_ml_prep.py -i GEOC -n{downsampling} -f{frame}")                                                   # This creates the files in GEOCmlXXX, including the png preview of unw

    # LiCSBAS03 - GACOS
    # CSBAS04 - mask    
    # LiCSBAS05 - clip
    #os.system(f"LiCSBAS05op_clip_unw.py -i {GEOCmldir} -o {'GEOCmldirclip'} -g {-91.5/-90.5/-0.6/-1.07}")                   # west east north south, can't get to work

    # LiCSBAS11 - check unwrapping, based on coherence
    os.system(f"LiCSBAS11_check_unw.py -d {GEOCmldir} -t {TSdir} -c {p11_coh_thre} -u {p11_unw_thre}")

    # LiCSBAS12 - check unwrapping, based on loop closure
    os.system(f"LiCSBAS12_loop_closure.py -d {GEOCmldir} -t {TSdir} -l {p12_loop_thre}")

    # LiCSBAS13 - SB inversion
    os.system(f"LiCSBAS13_sb_inv.py -d{GEOCmldir} -t{TSdir} --inv_alg {p13_inv_alg} --mem_size {p13_mem_size} --gamma {p13_gamma} --n_core {p13_n_core} --n_unw_r_thre {p13_n_unw_r_thre} --keep_incfile {p13_keep_incfile} " )

    # LiCSBAS 14 - velocity standard dev
    # LiCSBAS 15 - mask using noise indicies
    # LiCSBAS 16 - fiter
    

#%%
def LiCSBAS_to_LiCSAlert(h5_file, figures = False, n_cols=5, crop_pixels = None, return_r3 = False):
    """ A function to prepare the outputs of LiCSBAS for use with LiCSALERT.
    LiCSBAS uses nans for masked areas - here these are converted to masked arrays

    Inputs:
        h5_file | string | path to h5 file.  e.g. cum_filt.h5
        figures | boolean | if True, make two figures
        n_cols  | int | number of columns for figures.  May want to lower if plotting a long time series
        crop_pixels | tuple | coords to crop images to.  Note than in matrix style, so 00 is top left.  e.g. (10, 500, 600, 900).  No checking that inputted values make sense
        return_r3 | boolean | if True, the rank 3 data is also returns (n_ifgs x height x width).  Not used by ICASAR, so default is False

    Outputs:
        displacment_r3 | dict | Keys: cumulative, incremental.  Stored as masked arrays.  Mask should be consistent through time/interferograms
        displacment_r2 | dict | Keys: cumulative, incremental, mask.  Stored as row vectors in arrays.  
        baseline_info | dict| imdates : acquisition dates as strings
                              daisy_chain : names of the daisy chain of ifgs, YYYYMMDD_YYYYMMDD
                             baselines : temporal baselines of incremental ifgs

    2019/12/03 | MEG | Written
    2020/01/13 | MEG | Update depreciated use of dataset.value to dataset[()] when working with h5py files from LiCSBAS
    2020/02/16 | MEG | Add argument to crop images based on pixel, and return baselines etc
    """

    import h5py as h5
    import numpy as np
    import numpy.ma as ma
    import matplotlib.pyplot as plt
    
    

    def rank3_ma_to_rank2(ifgs_r3, consistent_mask = False):
        """A function to take a time series of interferograms stored as a rank 3 array,
        and convert it into the ICA(SAR) friendly format of a rank 2 array with ifgs as
        row vectors, and an associated mask.

        For use with ICA, the mask must be consistent.

        Inputs:
            ifgs_r3 | r3 masked array | ifgs in rank 3 format
            consistent_mask | boolean | If True, areas of incoherence are consistent through the whole stack
                                        If false, a consistent mask will be made.  N.b. this step can remove the number of pixels dramatically.
        """

        #import pdb; pdb.set_trace()
        n_ifgs = ifgs_r3.shape[0]
        # 1: Deal with masking
        mask_coh_water = ifgs_r3.mask                                                               #get the mask as a rank 3, still boolean
        if consistent_mask:
            mask_coh_water_consistent = mask_coh_water[0,]                                             # if all ifgs are masked in the same way, just grab the first one
        else:
            mask_coh_water_sum = np.sum(mask_coh_water, axis = 0)                                       # sum to make an image that shows in how many ifgs each pixel is incoherent
            mask_coh_water_consistent = np.where(mask_coh_water_sum == 0, np.zeros(mask_coh_water_sum.shape),
                                                                          np.ones(mask_coh_water_sum.shape)).astype(bool)    # make a mask of pixels that are never incoherent
        ifgs_r3_consistent = ma.array(ifgs_r3, mask = ma.repeat(mask_coh_water_consistent[np.newaxis,], n_ifgs, axis = 0))                       # mask with the new consistent mask

        # 2: Convert from rank 3 to rank 2
        n_pixs = ma.compressed(ifgs_r3_consistent[0,]).shape[0]                                                        # number of non-masked pixels
        ifgs_r2 = np.zeros((n_ifgs, n_pixs))
        for ifg_n, ifg in enumerate(ifgs_r3_consistent):
            ifgs_r2[ifg_n,:] = ma.compressed(ifg)

        return ifgs_r2, mask_coh_water_consistent


    def ts_quick_plot(ifgs_r3, title):
        """
        A quick function to plot a rank 3 array of ifgs.
        Inputs:
            title | string | title
        """
        n_ifgs = ifgs_r3.shape[0]
        n_rows = int(np.ceil(n_ifgs / n_cols))
        fig1, axes = plt.subplots(n_rows,n_cols)
        fig1.suptitle(title)
        for n_ifg in range(n_ifgs):
            ax=np.ravel(axes)[n_ifg]                                                                            # get axes on it own
            matrixPlt = ax.imshow(ifgs_r3[n_ifg,],interpolation='none', aspect='equal')                         # plot the ifg
            ax.set_xticks([])
            ax.set_yticks([])
            fig1.colorbar(matrixPlt,ax=ax)                                                                       
            ax.set_title(f'Ifg: {n_ifg}')
        for axe in np.ravel(axes)[(n_ifgs):]:                                                                   # delete any unused axes
            axe.set_visible(False)

    def daisy_chain_from_acquisitions(acquisitions):
        """Given a list of acquisiton dates, form the names of the interferograms that would create a simple daisy chain of ifgs.  
        Inputs:
            acquisitions | list | list of acquistiion dates in form YYYYMMDD
        Returns:
            daisy_chain | list | names of daisy chain ifgs, in form YYYYMMDD_YYYYMMDD
        History:
            2020/02/16 | MEG | Written
        """
        daisy_chain = []
        n_acqs = len(acquisitions)
        for i in range(n_acqs-1):
            daisy_chain.append(f"{acquisitions[i]}_{acquisitions[i+1]}")
        return daisy_chain
    
        
    def baseline_from_names(names_list):
        """Given a list of ifg names in the form YYYYMMDD_YYYYMMDD, find the temporal baselines in days_elapsed
        Inputs:
            names_list | list | in form YYYYMMDD_YYYYMMDD
        Returns:
            baselines | list of ints | baselines in days
        History:
            2020/02/16 | MEG | Documented 
        """
        from datetime import datetime
        
        baselines = []
        for file in names_list:
            master = datetime.strptime(file.split('_')[-2], '%Y%m%d')   
            slave = datetime.strptime(file.split('_')[-1][:8], '%Y%m%d')   
            baselines.append(-1 *(master - slave).days)    
        return baselines


    displacement_r3 = {}                                                                                        # here each image will 1 x width x height stacked along first axis
    displacement_r2 = {}                                                                                        # here each image will be a row vector 1 x pixels stacked along first axis
    baseline_info = {}

    cumh5 = h5.File(h5_file,'r')                                                                                # open the file from LiCSBAS
    baseline_info["imdates"] = cumh5['imdates'][()].astype(str).tolist()                                                         # get the acquisition dates
    cumulative = cumh5['cum'][()]                                                                               # get cumulative displacements
    
   
    if crop_pixels is not None:
        print(f"Cropping the images in x from {crop_pixels[0]} to {crop_pixels[1]} and in y from {crop_pixels[2]} to {crop_pixels[3]} (NB matrix notation - 0,0 is top left.  ")
        cumulative = cumulative[:, crop_pixels[2]:crop_pixels[3], crop_pixels[0]:crop_pixels[1]]                        # note rows first (y), then columns (x)
  
    mask_coh_water = np.isnan(cumulative)                                                                       # get where masked
    displacement_r3["cumulative"] = ma.array(cumulative, mask=mask_coh_water)                                   # rank 3 masked array of the cumulative displacement
    displacement_r3["incremental"] = np.diff(displacement_r3['cumulative'], axis = 0)                           # displacement between each acquisition - ie incremental
    n_im, length, width = displacement_r3["cumulative"].shape                                   

    if figures:                                                 
        ts_quick_plot(displacement_r3["cumulative"], title = 'Cumulative displacements')
        ts_quick_plot(displacement_r3["incremental"], title = 'Incremental displacements')

    # convert the data to rank 2 format (for both incremental and cumulative)
    displacement_r2['cumulative'], displacement_r2['mask'] = rank3_ma_to_rank2(displacement_r3['cumulative'])      # convert from rank 3 to rank 2 and a mask
    displacement_r2['incremental'], _ = rank3_ma_to_rank2(displacement_r3['incremental'])                          # also convert incremental, no need to also get mask as should be same as above

    # work with the acquisiton dates to produces names of daisy chain ifgs, and baselines
    baseline_info["daisy_chain"] = daisy_chain_from_acquisitions(baseline_info["imdates"])
    baseline_info["baselines"] = baseline_from_names(baseline_info["daisy_chain"])
    baseline_info["baselines_cumulative"] = np.cumsum(baseline_info["baselines"])                                         # cumulative baslines, e.g. 12 24 36 48 etc

    if return_r3:
        return displacement_r3, displacement_r2, baseline_info
    else:
        return displacement_r2, baseline_info



#%%
    
def detect_new_ifgs(path, initiate = False, ifgs_preexisting = None):
    """ Determine the number of LiCSAR ifgs in a folder, and detect if this changes.  
    Inputs:
        path | string | Path to LICSAR products (YYYYMMDD_YYYYMMDD folders) 
        initiate | boolean | if True, gets a list of ifgs and doens't check for new one 
                             if False, gets list of ifgs, compares with existing ifgs, and determines if any are new
         ifgs_preexisting | list of strings | only needed if not in iniatiate mode.  
         
    Returns (in initiate mode):
        ifgs_current | list of strings | current ifgs
        n_ifgs_current | int | number of LiCSAR ifgs       
    Returns (not in initiate mode):
        new_ifgs_flag | boolean | True if new ifgs have been added
        ifgs_current | list of strings | Ifgs now in the folder given by path.  
        new_ifgs | list of strings | Names of the new ifgs

    History:
        2020/02/18 | MEG |  Written        
            

    """
    import os 
    
    ifgs_current = sorted([f.name for f in os.scandir(path) if f.is_dir()])     # get names of folders produced by LiCSAR, and keep chronological.  
    n_ifgs_current = len(ifgs_current)                                          # and the number of them
    
    if initiate == True:                                                        # in initiation mode, just get the ifgs that are there and don't need to test for more
        return ifgs_current, n_ifgs_current
    
    elif initiate == False:                                                     # or in normal mode, point of this function is to detect if new ifgs have been added by LiCSAR automatic processing
        n_ifgs_preexisting = len(ifgs_preexisting)                              # get the number of ifgs that existed before the function was called
        
        if n_ifgs_current > n_ifgs_preexisting:                                 # check if we now have more ifgs.  
            new_ifgs_flag = True
            ifgs_new = []                                                       # list to store names of new ifgs
            for ifg in ifgs_current:                                            # loop through the current ifgs
                if ifg not in ifgs_preexisting:                                 # and if they're not in the list of prexisting ifgs
                    ifgs_new.append(ifg)                                        # add them to the list of new ifgs
            ifgs_new = sorted(ifgs_new)                                         # easier to use if remains chronological
            
        else:
            new_ifgs_flag = False                                               # or, if no new ifgs, set flag to false
            ifgs_new = []                                                       # and ifgs_new empty as no new ones
        
        return new_ifgs_flag, ifgs_current, ifgs_new
        
    else:                                                                                   # incase inititate is not set correctly.  
        raise Exception(f"'initiate' must be either 'True' or 'False'.  Exiting...")


#%%
    
def LiCSAlert_preprocessing(displacement_r2, downsample_run=1.0, downsample_plot=0.5, verbose=True):
    """A function to downsample the data at two scales (one for general working [ie to speed things up], and one 
    for faster plotting.  )  Also, data are mean centered, which is required for ICASAR and LiCSAlert.  
    Note that the downsamples are applied consecutively, so are compound.  
    
    Inputs:
        displacement_r2 | dict | input data stored in a dict as row vectors with a mask
        downsample_run | float | in range [0 1], and used to downsample the "incremental" data
        downsample_plot | float | in range [0 1] and used to downsample the data again for the "incremental_downsample" data
        
    Outputs:
        displacement_r2 | dict | input data stored in a dict as row vectors with a mask
                                 updated so that "incremental" is downsampled (and its mask), 
                                 and a new key is created, called "incremental_downsampled" 
                                 that is downsamled further for fast plotting                                 
    History:
        2020/01/13 | MEG | Written
    """
    import numpy as np
    from downsample_ifgs import downsample_ifgs

    
    n_pixs_start = displacement_r2["incremental"].shape[1]                                          # as ifgs are row vectors
    shape_start = displacement_r2["mask"].shape
    
    displacement_r2["incremental"] = displacement_r2["incremental"] - np.mean(displacement_r2["incremental"], axis = 1)[:,np.newaxis]                            # mean centre the data (along rows) 

    displacement_r2["incremental"], displacement_r2["mask"] = downsample_ifgs(displacement_r2["incremental"], displacement_r2["mask"],
                                                                                                         downsample_run)

    displacement_r2["incremental_downsampled"], displacement_r2["mask_downsampled"] = downsample_ifgs(displacement_r2["incremental"], displacement_r2["mask"],
                                                                                                         downsample_plot)
    if verbose:
        print(f"Interferogram were originally {shape_start} ({n_pixs_start} unmasked pixels), "
              f"but have been downsamped to {displacement_r2['mask'].shape} ({displacement_r2['incremental'].shape[1]} unmasked pixels) for use with LiCSAlert, "
              f"and have been downsamped to {displacement_r2['mask_downsampled'].shape} ({displacement_r2['incremental_downsampled'].shape[1]} unmasked pixels) for figures.  ")


    return displacement_r2



#%%
def bss_components_inversion(sources, interferograms, cumulative = True):
    """
    A function to fit an interferogram using components learned by BSS, and return how strongly
    each component is required to reconstruct that interferogramm, and the

    Inputs:
        sources | n_sources x pixels | ie architecture I.  Mean centered
        interferogram | n_ifgs x pixels | Doesn't have to be mean centered, ifgs are rows
        cumulative | Boolean | if true, m and residual (mean_l2_norm) are returned as cumulative sums.

    Outputs:
        m | rank 1 array | the strengths with which to use each source to reconstruct the ifg.
        mean_l2norm | float | the misfit between the ifg and the ifg reconstructed from sources

    2019/12/30 | MEG | Update so handles time series (and not single ifgs), and can return cumulative values
    """
    import numpy as np

    interferograms -= np.mean(interferograms)                     # mean centre
    (n_ifgs, n_pixels) = interferograms.shape

    d = interferograms.T                                                 # a column vector (p x 1)
    g = sources.T                                                       # a matrix of ICA sources and each is a column (p x n_sources)
    m = np.linalg.inv(g.T @ g) @ g.T @ d                                # m (n_sources x n_ifgs)
    d_hat = g@m                                                         # reconstructed ifgs, as column vectors
    d_resid = d - d_hat                                                 # residual between each ifg and its reconstruction

    m = m.T                                                             # make these column vectors
    residual = np.zeros((n_ifgs,1))                                     # residuals, as column vectors
    for i in range(n_ifgs):
        residual[i,] = np.sqrt(np.sum(d_resid[:,i]**2))/n_pixels         # the mean l2 norm for each ifg

    if cumulative:
        m = np.cumsum(m, axis=0)
        residual = np.cumsum(residual, axis=0)
    return m, residual


#%%
def time_course_rescaler(timecourses, temp_baselines):
    """A script to normalise timecourses so that ones that span long temporal baselines are normalised
    
    Neer finished?
    
    Inputs:
        timecourses | 2d array | as column (e.g. 77x5)
        temp_baselines | 2d array | as a column

    Outputs:
        timecourses | 2d array | as column (e.g. 77x5)
    """

    # timecourses_scaled = 12 * np.divide(timecourses, temp_baselines)                    # x12 so that no change for normal S1 12 day baseline
    # return timecourses_scaled




#%%
def filenames_to_baselines(phUnw_files):
    """
    Given a list of LiCSAR filenames, works out the temporal baselines from these.
    Inputs:
        phUnw_files | lst of strings | filename of each interferogram

    Outputs:
        baselines | column vector of temporal baselines
        baselines_cumulative | column vector of the cumulative sum of the baselines

    2017/12/1? | written as a script
    2017/12/19 | converte to a function
    2018/07/31 | update how dates are removed from filename to work with geocoded data (.geo.unw)
    2018/08/21 | change in format of how dates are removed.

    """
    import datetime
    import nump as np

    baselines = np.zeros((len(phUnw_files),1))

    i = 0
    for filename in phUnw_files:
        master_date = filename[:8]
        slave_date = filename[9:17]

        fmt = '%Y%m%d'                                                                      # tell datetime the format of the date (here year, month, day with no sepeartions)
        master_date_dt = datetime.datetime.strptime(master_date, fmt)
        master_date_tt = master_date_dt.timetuple()
        slave_date_dt = datetime.datetime.strptime(slave_date, fmt)
        slave_date_tt = slave_date_dt.timetuple()

        if master_date_tt.tm_year == slave_date_tt.tm_year:                                 # most ifgs don't span new year so are easy to deal with
            temporal_baseline = slave_date_tt.tm_yday - master_date_tt.tm_yday
        else:                                                                               # some do
            if master_date_tt.tm_year == 2016:                                              # and some could span leap years
                n_year_days = 366
            else:
                n_year_days = 365
            temporal_baseline = slave_date_tt.tm_yday + (n_year_days - master_date_tt.tm_yday)

        baselines[i,:] = temporal_baseline
        i += 1

    baselines_cumulative = np.cumsum(baselines)
    return baselines, baselines_cumulative


#%%
    
def save_pickle(fileout_name, *argv):
    """Save any number of items to a pickle file.  
    Inputs:
        fileout_name | str | filename
        *argv | items to be saved in pickle
    Outputs:
        fileout_name.pkl
    """
    import pickle

    with open(f"{fileout_name}.pkl", 'wb') as f:
        for arg in argv:                                        # loop through all inputs and save
            pickle.dump(arg, f)

  
    
#%%
            
def shorten_LiCSAlert_data(displacement_r2, n_end, n_start=0, verbose=False):
    """ Given a dictionary of ifgs for use with LiCSAlert, crop temporally (ie. the fist/vertical axis).  
    Inputs:
        displacement_r2 | dict | displacement is stored as row vectors in this
        n_end | int | ifg number to stop cropping at
        n_start | int | ifg number to start croppting at
        verbose | boolean | 
        
    Returns:
        displacement_r2_short | dict | as per input, but temporally cropped
        
    History:
        2020/01/10 | MEG  | Written
    """    
    import copy                                                                                                # needed to deepcopy dict
    displacement_r2_short = copy.deepcopy(displacement_r2)
    keys_to_shorten = ["incremental", "incremental_downsampled"]                                                    # only these items in the dict will be cropped
    for key_to_shorten in keys_to_shorten:
        try:
            displacement_r2_short[key_to_shorten] = displacement_r2_short[key_to_shorten][n_start:n_end,]
            if verbose:
                print(f"Succesfuly shortened {key_to_shorten} in the dictionary of interferograms")
        except:
            pass
            if verbose:
                print(f"{key_to_shorten} was not found in the dictionary of interferograms")
    return displacement_r2_short


#%% Small functions used by multiple function in this file
    
                     
def col_to_ma(col, pixel_mask):
    """ A function to take a column vector and a 2d pixel mask and reshape the column into a masked array.  
    Useful when converting between vectors used by BSS methods results that are to be plotted
    Inputs:
        col | rank 1 array | 
        pixel_mask | array mask (rank 2)
    Outputs:
        source | rank 2 masked array | colun as a masked 2d array
    2017/10/04 | collected from various functions and placed here.  
    """
    import numpy.ma as ma 
    import numpy as np
    
    source = ma.array(np.zeros(pixel_mask.shape), mask = pixel_mask )
    source.unshare_mask()
    source[~source.mask] = col.ravel()   
    return source